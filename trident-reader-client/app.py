# standard
from asyncio import run, Future, get_event_loop, new_event_loop, set_event_loop, sleep, wait_for, TimeoutError
from threading import Thread
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, LoggerAdapter
from requests import post
from requests import codes
from traceback import format_exception_only

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

# stop_reader flag
stop_reader = False

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

def check_update_status(newstatus):
    global detailedstatus
    
    laststatus = detailedstatus
    detailedstatus = newstatus
    if detailedstatus != laststatus:
        # set reader_id appropriately for #82
        rsp = post(chipstatuspost, json={'status':detailedstatus, 'reader_id':'A'})
        if rsp.status_code != codes.ok:
            log.error(f'error sending to backend: status = {rsp.status_code}')
        else:
            respdata = loads(rsp.text)
            if respdata['status'] != 'success':
                log.error(f'error sending to backend: response = {respdata["error"]}')

async def shell(reader, writer):
    global stop_reader

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
        check_update_status('disconnected')
        return

def reader_thread(ipaddr, fport, logging_path):
    log.info(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)
    
    try:
        coro = open_connection(ipaddr, fport, shell=shell)
        reader, writer = readloop.run_until_complete(coro)
        readloop.run_until_complete(writer.protocol.waiter_closed)
    
    except Exception as e:
        # report exception
        exc = ''.join(format_exception_only(type(e), e))
        log.error(f'exception occurred opening connection - {exc}')
        
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