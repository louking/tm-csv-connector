# standard
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, LoggerAdapter
from requests import post
from requests import codes

# pypi
from websockets.server import serve

# homegrown
from ..tm_csv_connector.model import ChipRead

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
backendpost = 'http://tm.localhost:8080/_postchipread'

# connection status is global -- is there any way to get a class status from an async protocol?
connected = False

# stop_reader flag
stop_reader = False

# queue messages from input protocol for sending to backend
queued_msgs = []

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

class TcpChunkProtocol(Protocol):
    """adapted from https://pyserial-asyncio.readthedocs.io/en/latest/shortintro.html#serial-transports-protocols-and-streams

    handle serial protocol input
    
    Args:
        Protocol (asyncio.Protocol): 
    """
    def __init__(self):
        super().__init__()
        self.log_handler = None
        global connected
        connected = False
    
    '''read from trident reader, adapted from 
    https://pyserial-asyncio.readthedocs.io/en/latest/shortintro.html#reading-data-in-chunks'''
    def connection_made(self, transport):
        self.transport = transport
        self.residual = b''
        global connected
        connected = True
    
    def connection_lost(self, exc: Exception | None) -> None:
        global connected
        connected = False
        
        return super().connection_lost(exc)

    def data_received(self, data):
        log.debug(f'trident reader data received: {data}')
        
        # update first part of data with residual
        data = self.residual + data

        # split into separate messages -- scanner default is to append two CR to end of scanned barcode, allow one  
        msgs = data.split(b'\r')
        
        # last part is saved for later, may be empty, don't send to back end
        # note the residual may be the only item in msgs
        self.residual = msgs.pop()
        if self.residual:
            log.debug(f'trident reader residual: {self.residual}')
        
        # send each relevant message to the database
        for msg in msgs:
            # skip empty or uninteresting msg
            if not msg or msg[0:2] not in ['aa', 'ab']: continue
            
            log.debug(f'trident reader msg processed: {msg}')
            # need to decode bytes type
            queued_msgs.append(msg)
        
        # stop callbacks again immediately
        self.pause_reading()

    def pause_reading(self):
        # This will stop the callbacks to data_received
        self.transport.pause_reading()

    def resume_reading(self):
        # This will start the callbacks to data_received again with all data that has been received in the meantime.
        self.transport.resume_reading()
    
    def set_logging_path(self, logging_path):
        self.logging_path = logging_path
        log.error(f'need to set logging path in logger')
        
def save_read_to_db(data):
    """save relevant chip reads to the database

    Args:
        data (dict): dict to serialize and send
    """
    log.debug(f'sending to backend: {data}')
    rsp = post(backendpost, json=data)
    if rsp.status_code != codes.ok:
        log.error(f'error sending to backend: status = {rsp.status_code}')
    else:
        respdata = loads(rsp.text)
        if respdata['status'] != 'success':
            log.error(f'error sending to backend: response = {respdata["error"]}')
        
async def reader(port, logging_path):
    log.info(f'trident reader async reader started with port {port}')
    readloop = get_event_loop()
    transport, protocol = await create_serial_connection(readloop, TcpChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    try:
        while True:
            global stop_reader
            if stop_reader:
                log.info('trident reader reader stopped')
                stop_reader = False
                transport.close()
                raise ReaderClosed
            
            await sleep(0.3)
            
            # send any queued messages
            global queued_msgs
            if queued_msgs:
                while len(queued_msgs) > 0:
                    msg = queued_msgs.pop(0)
                    save_read_to_db(msg)

            protocol.resume_reading()
    
    except ReaderClosed:
        return

def reader_thread(port, logging_path):
    log.info(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)
    run(reader(port, logging_path))
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
        if opcode in ['open', 'close', 'raceid']:
            log.debug(f'websocket received {event}')
        
        # backend opened the connection
        if opcode == 'open':
            port = event['port']
            logging_path = event['loggingpath']
            readloop_threadid = Thread(target=reader_thread, args=(port, logging_path)).start()
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
            await websocket.send(dumps({'connected': connected}))

async def main():
    async with serve(controller, host="localhost", port=8082):
        await Future() # run forever
    
if __name__ == "__main__":
    try:
        run(main())
    except KeyboardInterrupt:
        log.info('barcode-scanner exiting')