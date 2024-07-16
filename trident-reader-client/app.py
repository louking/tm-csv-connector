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

# connection status is global -- is there any way to get a class status from an async protocol?
connected = False

# stop_reader flag
stop_reader = False

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
    """save relevant chip reads to the database

    Args:
        data (dict): dict to serialize and send
    """
    log.debug(f'sending to backend: {data}')
    rsp = post(backendpost, json={'data':data})
    if rsp.status_code != codes.ok:
        log.error(f'error sending to backend: status = {rsp.status_code}')
    else:
        respdata = loads(rsp.text)
        if respdata['status'] != 'success':
            log.error(f'error sending to backend: response = {respdata["error"]}')
        
async def shell(reader, writer):
    log.info(f'trident telnet shell entered')
    readloop = get_event_loop()
    # protocol.set_logging_path(logging_path)
    SEP = '\r\n'
    
    residual = ''
    
    try:
        while True:
            global stop_reader
            if stop_reader:
                log.info('trident reader reader stopped')
                stop_reader = False
                raise ReaderClosed
            
            # read anything which came in, but don't wait too long
            # https://stackoverflow.com/a/76405900/799921
            try:
                # let some messages come in for a bit
                await sleep(1)
                # timeout allows this not to hang if no data, so we can get the stop_reader control
                # make sure the buffer is big enough to handle the sleep's worth of data
                data = await wait_for(reader.read(4096), timeout=0.1)
                msgs = residual + data

                # split into messages for ease of residual processing
                # the last bit didn't end in SEP, or is empty
                splitmsgs = msgs.split(SEP)
                residual = splitmsgs.pop()
                
                # send any received messages
                if splitmsgs:
                    save_reads_to_db(SEP.join(splitmsgs))

            except TimeoutError:
                pass
            
            finally:
                # connection management
                global connected
                connected = not (reader.at_eof() or writer.connection_closed)
                if not connected:
                    log.info('discovered connection closed; stopping trident reader')
                    stop_reader = False
                    raise ReaderClosed
                    

    except ReaderClosed:
        reader.feed_eof()
        writer.close()
        connected = False
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
        if opcode in ['open', 'close']:
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
        
        # browser wants to know if we're connected to trident reader
        elif opcode == 'is_connected':
            await websocket.send(dumps({'connected': connected}))

async def main():
    async with serve(controller, host="localhost", port=8083):
        await Future() # run forever
    
if __name__ == "__main__":
    try:
        run(main())
    except KeyboardInterrupt:
        log.info('trident-reader-client exiting')