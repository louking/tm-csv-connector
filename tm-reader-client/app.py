# standard
from sys import stdout
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread
from json import loads, dumps
from logging import getLogger, DEBUG, StreamHandler, Formatter
from logging.handlers import TimedRotatingFileHandler

# pypi
from websockets import connect
from websockets.server import serve
from serial_asyncio import create_serial_connection

log = getLogger('tm-csv-connector')
log.setLevel(DEBUG)
handler = StreamHandler(stdout)
handler.setLevel(DEBUG)
formatter = Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)

backenduri = 'ws://tm.localhost:8080/tm_reader'
PRIMARY = b'\x17'
SELECT  = b'\x14'

# connection status is global -- is there any way to get a class status from an async protocol?
connected = False

# stop_reader flag
stop_reader = False

# queue messages from input protocol for sending to backend
queued_msgs = []

class InputChunkProtocol(Protocol):
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
    
    '''read from time machine, adapted from 
    https://pyserial-asyncio.readthedocs.io/en/latest/shortintro.html#reading-data-in-chunks'''
    def connection_made(self, transport):
        self.transport = transport
        self.residual = b''
        global connected
        connected = True
        # with connect(backenduri) as websocket:
        #     await self.send_to_backend(websocket, {'opcode': 'connected'})
    
    def connection_lost(self, exc: Exception | None) -> None:
        global connected
        connected = False
        # with connect(backenduri) as websocket:
        #     await self.send_to_backend(websocket, {'opcode': 'disconnected'})
        
        return super().connection_lost(exc)

    def data_received(self, data):
        log.debug(f'data received: {data}')
        msgs = data.split(b'\r\n')
        
        # update first part of data with residual, making sure there's at least one item in msgs
        if len(msgs) > 0:
            msgs[0] = self.residual + msgs[0]
        else:
            msgs = [self.residual]
        
        # last part is saved for later, may be empty, don't send to back end
        # note the residual may be the only item in msgs
        self.residual = msgs.pop()
        
        # don't connect if nothing to send
        if msgs:
            # connect to websocket, send each relevant message to the back end
            # relevant message format on p3-1 of Time Machine User Manual
            # assumes cross-country mode is used
            for msg in msgs:
                try:
                    # split message into parts
                    control = msg[0:1]
                    if control in [PRIMARY, SELECT]:
                        pos = int(msg[9:13])
                        time = msg[14:26].decode().strip()
                    
                        # check control character; queue message for handling in the background
                        global queued_msgs
                        if control == PRIMARY:
                            queued_msgs.append({'opcode': 'primary', 'pos': pos, 'time': time})
                        elif control == SELECT:
                            bib = int(msg[29:33].decode())
                            queued_msgs.append({'opcode': 'select', 'pos': pos, 'time': time, 'bib': bib})
                except ValueError:
                    log.error(f'could not decode message: {msg}')
        
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
        
async def send_to_backend(websocket, data):
    """send data to backend

    Args:
        websocket (websocket): websocket to send to
        data (dict): dict to serialize and send
    """
    sending = dumps(data)
    log.debug(f'sending: {sending}')
    log.debug(f'websocket.send = {websocket.send}')
    await websocket.send(sending)
        
async def reader(port, logging_path):
    log.debug(f'async reader started with port {port}')
    readloop = get_event_loop()
    transport, protocol = await create_serial_connection(readloop, InputChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    while True:
        global stop_reader
        if stop_reader:
            log.debug('reader stopped')
            stop_reader = False
            transport.close()
            break
        
        await sleep(0.3)
        
        # send any queued messages
        global queued_msgs
        if queued_msgs:
            async with connect(backenduri) as websocket:
                while len(queued_msgs) > 0:
                    msg = queued_msgs.pop(0)
                    await send_to_backend(websocket, msg)

        protocol.resume_reading()

def reader_thread(port, logging_path):
    log.debug(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)
    # readloop.run_until_complete(reader(port, logging_path))
    # readloop.close()
    run(reader(port, logging_path))
    log.debug('exiting reader_thread()')
    
async def controller(websocket):
    """server for control commands

    Args:
        websocket (websocket): websocket from backend client
    """
    async for message in websocket:
        event = loads(message)
        opcode = event['opcode']
        if opcode in ['open', 'close']:
            log.debug(f'received {event}')
        if opcode == 'open':
            port = event['port']
            logging_path = event['loggingpath']
            readloop_threadid = Thread(target=reader_thread, args=(port, logging_path)).start()
            # readloop = get_event_loop()
            # readloop.run_until_complete(reader(port, logging_path))
            log.debug('returned from Thread')
        elif opcode == 'close':
            # readloop = get_event_loop()
            # readloop.stop()
            # readloop.close()
            # readloop = None
            global stop_reader
            stop_reader = True
            global connected
            connected = False
        elif opcode == 'is_connected':
            await websocket.send(dumps({'connected': connected}))

async def main():
    async with serve(controller, host="localhost", port=8081):
        await Future() # run forever
    
if __name__ == "__main__":
    run(main())