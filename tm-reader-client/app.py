# standard
from asyncio import run, Future, Protocol, sleep, get_event_loop
from json import loads, dumps
from logging import getLogger, INFO
from logging.handlers import TimedRotatingFileHandler

# pypi
from websockets import connect, serve, ConnectionClosedOK
from serial_asyncio import create_serial_connection
readloop = None
log = getLogger('tm-csv-connector')
log.setLevel(INFO)

backenduri = 'http://localhost:8080/ws'
PRIMARY = b'\x17'
SELECT  = b'\x14'

class InputChunkProtocol(Protocol):
    def __init__(self):
        super().__init__()
        self.log_handler = None
    
    def send_to_backend(self, websocket, data):
        """send data to backend

        Args:
            websocket (websocket): websocket to send to
            data (dict): dict to serialize and send
        """
        sending = dumps({'opcode': 'connected'})
        log.debug(f'InputChunkProtocol sending: {data}')
        websocket.send(sending)
        
    '''read from time machine, adapted from 
    https://pyserial-asyncio.readthedocs.io/en/latest/shortintro.html#reading-data-in-chunks'''
    def connection_made(self, transport):
        self.transport = transport
        self.residual = b''
        with connect(backenduri) as websocket:
            self.send_to_backend(websocket, {'opcode': 'connected'})
    
    def connection_lost(self, exc: Exception | None) -> None:
        with connect(backenduri) as websocket:
            self.send_to_backend(websocket, {'opcode': 'disconnected'})
        
        return super().connection_lost(exc)

    def data_received(self, data):
        print('data received', repr(data))
        msgs = data.split(b'\r\n')
        
        # update first part of data with residual, making sure there's at least one item in msgs
        if len(msgs) > 0:
            msgs[0] = self.residual + msgs[0]
        else:
            msgs = [self.residual]
        
        # last part is saved for later, may be empty, don't send to back end
        # note the residual may be the only item in msgs
        self.residual = msgs[-1]
        msgs.pop()
        
        # don't connect if nothing to send
        if msgs:
            # connect to websocket, send each relevant message to the back end
            # relevant message format on p3-1 of Time Machine User Manual
            # assumes cross-country mode is used
            with connect(backenduri) as websocket:
                for msg in msgs:
                    try:
                        # split message into parts
                        control = msg[0]
                        pos = int(msg[9:13])
                        time = msg[14:26].decode()
                        
                        # check control character
                        if control == PRIMARY:
                            self.send_to_backend(websocket, {'opcode': 'primary', 'pos': pos, 'time': time})
                        elif control == SELECT:
                            bib = int(msg[29:33].decode())
                            self.send_to_backend(websocket, {'opcode': 'select', 'pos': pos, 'time': time, 'bib': bib})
                    except ValueError:
                        print(f'could not decode message: {msg}')
        
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
        

async def reader(port, logging_path):
    transport, protocol = await create_serial_connection(readloop, InputChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    while True:
        await sleep(0.3)
        protocol.resume_reading()

async def controller(websocket):
    """server for control commands

    Args:
        websocket (websocket): websocket from backend client
    """
    async for message in websocket:
        event = loads(message)
        if event['opcode'] == 'open':
            readloop = get_event_loop()
            readloop.run_forever(reader(event['port'], event['loggingpath']))
        elif event['opcode'] == 'close':
            readloop.close()
            readloop = None
        print(message)

async def main():
    async with serve(controller, host="localhost", port=8081):
        await Future() # run forever
    
if __name__ == "__main__":
    run(main())