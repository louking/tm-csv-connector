# standard
from asyncio import run, Future, get_event_loop, new_event_loop, set_event_loop, sleep, wait_for, TimeoutError
from threading import Thread
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, LoggerAdapter
from requests import post
from requests import codes
from traceback import format_exception_only
import socket

# pypi
from websockets.server import serve
from telnetlib3 import open_connection
from ping3 import ping

class ReaderClosed(Exception): pass

basicConfig(
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    level=DEBUG,
)

log = getLogger('trident-reader')

# these should be configurable
getLogger('websockets.client').setLevel(INFO)
getLogger('websockets.server').setLevel(INFO)

backenduri = 'ws://tm.localhost:8080/trident_reader'
backendpost = 'http://tm.localhost:8080/_livechipreads'
chipstatuspost = 'http://tm.localhost:8080/_chipreaderstatus'

# connection status is global
connected = False

# detailed status is global, values must match api.py and results.js
detailedstatus = 'disconnected'

# a candidate status must be observed this many consecutive times before it's
# reported -- avoids logging a status change for a single transient ping blip
STATUS_DEBOUNCE_COUNT = 3
pending_status = None
pending_count = 0

# stop_reader flag
stop_reader = False

# set immediately before a user-requested close raises ReaderClosed, so
# reader_thread() can tell "user clicked disconnect" apart from "connection
# was lost unexpectedly" and only auto-retry the latter
user_closed = False

# true while reader_thread() is alive (actively connected or auto-retrying),
# guards against a duplicate 'open' opcode spawning a second thread
reader_thread_running = False

# seconds to wait between auto-reconnect attempts after an unexpected drop
RECONNECT_WAIT = 5

# TCP keepalive timing -- short enough to notice a half-dead connection
# (reader rebooted without sending FIN/RST) within tens of seconds, since a
# bare ping success can't tell a live socket from a stale one
KEEPALIVE_IDLE_SEC = 10
KEEPALIVE_INTERVAL_SEC = 5
KEEPALIVE_COUNT = 3

# save latest raceid
raceid = 0

class LoggerAdapter(LoggerAdapter):
    """Add connection ID and client IP address to websockets logs."""
    def process(self, msg, kwargs):
        try:
            websocket = kwargs["extra"]["websocket"]
        except KeyError:
            return msg, kwargs
        if getattr(websocket, 'request_headers', None):
            xff = websocket.request_headers.get("X-Forwarded-For")
        else:
            xff = '??'
        return f"{websocket.id} {xff} {msg}", kwargs

def save_reads_to_db(data):
    """save relevant chip reads to the database, uses current raceid

    Args:
        data (dict): dict to serialize and send
    """
    log.debug(f'sending to backend: raceid {raceid}, data {data}')
    rsp = post(backendpost, json={'raceid': raceid, 'data': data})
    if rsp.status_code != codes.ok:
        log.error(f'error sending to backend: status = {rsp.status_code}')
    else:
        respdata = loads(rsp.text)
        if respdata['status'] != 'success':
            log.error(f'error sending to backend: response = {respdata["error"]}')

def check_update_status(newstatus, immediate=False):
    """update detailedstatus and notify backend, but debounce transient flips

    Args:
        newstatus (str): candidate status
        immediate (bool): bypass debounce, e.g. for a definitive one-shot
            event like the reader connection actually closing
    """
    global detailedstatus, pending_status, pending_count

    if newstatus == detailedstatus:
        pending_status = None
        pending_count = 0
        return

    if not immediate:
        if newstatus == pending_status:
            pending_count += 1
        else:
            pending_status = newstatus
            pending_count = 1

        if pending_count < STATUS_DEBOUNCE_COUNT:
            return

    detailedstatus = newstatus
    pending_status = None
    pending_count = 0

    # set reader_id appropriately for #82
    rsp = post(chipstatuspost, json={'status':detailedstatus, 'reader_id':'A'})
    if rsp.status_code != codes.ok:
        log.error(f'error sending to backend: status = {rsp.status_code}')
    else:
        respdata = loads(rsp.text)
        if respdata['status'] != 'success':
            log.error(f'error sending to backend: response = {respdata["error"]}')

def enable_keepalive(writer):
    """enable short-interval TCP keepalive on the reader socket

    A bare ping3 success only proves the reader's network stack answers
    ICMP, not that this specific telnet socket is still recognized by the
    peer -- if the reader reboots without ever sending FIN/RST, reads just
    time out forever while ping keeps reporting 'connected'. TCP keepalive
    makes the OS itself detect that and surface it as a real connection
    close (reader.at_eof() / writer.connection_closed), which is what
    triggers auto-reconnect.

    Args:
        writer (StreamWriter): writer for the just-opened connection
    """
    try:
        sock = writer.transport.get_extra_info('socket')
        if sock is None:
            log.warning('trident reader: could not get raw socket, keepalive not enabled')
            return
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError as e:
        log.warning(f'trident reader: failed to enable SO_KEEPALIVE: {e}')
        return

    try:
        if hasattr(socket, 'TCP_KEEPIDLE') and hasattr(socket, 'TCP_KEEPINTVL') and hasattr(socket, 'TCP_KEEPCNT'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_IDLE_SEC)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVAL_SEC)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_COUNT)
        elif hasattr(socket, 'SIO_KEEPALIVE_VALS'):
            # older Windows: no per-probe-count control, idle/interval in ms
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, KEEPALIVE_IDLE_SEC * 1000, KEEPALIVE_INTERVAL_SEC * 1000))
        else:
            log.warning('trident reader: no keepalive timing control on this platform, using OS defaults')
    except OSError as e:
        log.warning(f'trident reader: failed to tune keepalive timing: {e}')

async def shell(reader, writer):
    global stop_reader, user_closed

    log.info(f'trident telnet shell entered')
    readloop = get_event_loop()
    # protocol.set_logging_path(logging_path)
    SEP = '\r\n'
    
    residual = ''
    pingtime = 0
    ipaddr = writer.transport.get_extra_info('peername')[0]
    
    try:
        while True:
            if stop_reader:
                log.info('trident reader reader stopped')
                stop_reader = False
                user_closed = True
                raise ReaderClosed
            
            # read anything which came in, but don't wait too long
            # https://stackoverflow.com/a/76405900/799921
            try:
                # let some messages come in for a bit, don't sleep negative for long ping response
                await sleep(max(1-pingtime, 0))

                # timeout allows this not to hang if no data, so we can get the stop_reader control
                # make sure the buffer is big enough to handle the sleep's worth of data
                data = await wait_for(reader.read(4096), timeout=0.1)
                msgs = residual + data

                # if we received something, we're connected
                check_update_status('connected')

                # split into messages for ease of residual processing
                # the last bit didn't end in SEP, or is empty
                splitmsgs = msgs.split(SEP)
                residual = splitmsgs.pop()
                
                # send any received messages
                if splitmsgs:
                    save_reads_to_db(SEP.join(splitmsgs))

            except TimeoutError:
                pingtime = ping(ipaddr, timeout=1)
                # got a response -- we are connected
                if pingtime:
                    check_update_status('connected')
                
                else:
                    if pingtime == False:
                        check_update_status('network-unreachable')
                    else: # None
                        check_update_status('no-response')
                    pingtime = 1
            
            finally:
                # connection management
                global connected
                connected = not (reader.at_eof() or writer.connection_closed)
                if not connected:
                    log.info('discovered connection closed; stopping trident reader')
                    stop_reader = False
                    raise ReaderClosed
                    

    except (ReaderClosed, ConnectionAbortedError) as e:
        reader.feed_eof()
        writer.close()
        connected = False
        check_update_status('disconnected', immediate=True)
        return

def reader_thread(ipaddr, fport, logging_path):
    """connect to the trident reader, and keep reconnecting on unexpected drops

    Runs until the user explicitly disconnects (stop_reader / user_closed),
    retrying with a fixed backoff any time the connection is lost or can't be
    established in the first place (e.g., reader still powering on).

    Args:
        ipaddr (str): reader IP address
        fport (int): reader telnet port
        logging_path (str): unused, reserved for future use
    """
    global stop_reader, user_closed, reader_thread_running

    log.info(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)

    reader_thread_running = True
    try:
        while True:
            user_closed = False
            try:
                coro = open_connection(ipaddr, fport, shell=shell)
                reader, writer = readloop.run_until_complete(coro)
                enable_keepalive(writer)
                readloop.run_until_complete(writer.protocol.waiter_closed)

            except Exception as e:
                # report exception
                exc = ''.join(format_exception_only(type(e), e))
                log.error(f'exception occurred opening connection - {exc}')

            if user_closed:
                log.info('trident reader closed by user request')
                break

            if stop_reader:
                # disconnect requested while there was no live connection to catch it
                log.info('trident reader closed by user request during reconnect wait')
                stop_reader = False
                break

            log.info(f'trident reader connection lost unexpectedly; retrying in {RECONNECT_WAIT}s')
            readloop.run_until_complete(sleep(RECONNECT_WAIT))

    finally:
        reader_thread_running = False

    log.info('exiting reader_thread()')
    
async def controller(websocket):
    """server for control commands

    Args:
        websocket (websocket): websocket from backend client
    """
    async for message in websocket:
        event = loads(message)
        opcode = event['opcode']
        
        # just wanna know what's going on
        if opcode not in ['is_connected', 'ping']:
            log.debug(f'websocket received {event}')
        
        # backend opened the connection
        if opcode == 'open':
            if reader_thread_running:
                log.info('reader_thread already running (connected or auto-retrying); ignoring open')
            else:
                ipaddr = event['ipaddr']
                fport = event['fport']
                logging_path = event['loggingpath']
                readloop_threadid = Thread(target=reader_thread, args=(ipaddr, fport, logging_path)).start()
                log.info('controller returned from Thread')
        
        # backend closed the connection
        elif opcode == 'close':
            global stop_reader
            stop_reader = True
        
        # raceid updated from backend
        elif opcode == 'raceid':
            global raceid
            raceid = event['raceid']
        
        # browser wants to know if we're connected to trident reader
        elif opcode == 'is_connected':
            await websocket.send(dumps({'connected': connected, 'detailedstatus': detailedstatus}))

async def main():
    async with serve(controller, host="localhost", port=8083):
        await Future() # run forever
    
if __name__ == "__main__":
    try:
        run(main())
    except KeyboardInterrupt:
        log.info('trident-reader-client exiting')