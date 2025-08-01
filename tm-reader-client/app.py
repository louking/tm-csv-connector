# standard
from sys import stdout
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, StreamHandler, Formatter, LoggerAdapter
from logging.handlers import TimedRotatingFileHandler
from requests import post
from requests import codes
from serial.tools.list_ports import comports

# pypi
from websockets import connect, ConnectionClosed
from websockets.server import serve
from serial_asyncio import create_serial_connection

class ReaderClosed(Exception): pass

basicConfig(
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    level=DEBUG,
)

log = getLogger('tm-reader')
# log.setLevel(DEBUG)
# handler = StreamHandler(stdout)
# handler.setLevel(DEBUG)
# formatter = Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
# handler.setFormatter(formatter)
# log.addHandler(handler)

# these should be configurable
getLogger('websockets.client').setLevel(INFO)
getLogger('websockets.server').setLevel(INFO)

backenduri = 'ws://tm.localhost:8080/tm_reader'
backendpost = 'http://tm.localhost:8080/_postresult'
PRIMARY = b'\x17'
SELECT  = b'\x14'

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
        log.debug(f'time machine data received: {data}')
        
        # update first part of data with residual
        data = self.residual + data

        # split into separate messages            
        msgs = data.split(b'\r\n')
        
        # last part is saved for later, may be empty, don't send to back end
        # note the residual may be the only item in msgs
        self.residual = msgs.pop()
        if self.residual:
            log.debug(f'time machine residual: {self.residual}')
        
        # send each relevant message to the back end
        # relevant message format on p3-1 of Time Machine User Manual
        # assumes cross-country mode is used
        for msg in msgs:
            try:
                log.debug(f'time machine msg processed: {msg}')
                # split message into parts
                control = msg[0:1]
                if control in [PRIMARY, SELECT]:
                    pos = int(msg[8:13])
                    time = msg[13:24].decode()
                
                    # check control character; queue message for handling in the background
                    global queued_msgs
                    if control == PRIMARY:
                        queued_msgs.append({'opcode': 'primary', 'raceid': raceid, 'pos': pos, 'time': time})
                    elif control == SELECT:
                        bib = int(msg[27:32].decode())
                        queued_msgs.append({'opcode': 'select', 'raceid': raceid, 'pos': pos, 'time': time, 'bibno': bib})
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
        
def send_to_backend(data):
    """send data to backend

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
    log.info(f'time machine async reader started with port {port}')
    readloop = get_event_loop()
    transport, protocol = await create_serial_connection(readloop, InputChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    try:
        while True:
            global stop_reader
            if stop_reader:
                log.info('time machine reader stopped')
                stop_reader = False
                transport.close()
                raise ReaderClosed
            
            await sleep(0.3)
            
            # send any queued messages
            global queued_msgs
            if queued_msgs:
                while len(queued_msgs) > 0:
                    msg = queued_msgs.pop(0)
                    send_to_backend(msg)

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
        if opcode in ['open', 'close', 'raceid', 'get_comports']:
            log.debug(f'websocket received {event}')
        
        # backend opened the connection
        if opcode == 'open':
            port = event['port']
            logging_path = event['loggingpath']
            readloop_threadid = Thread(target=reader_thread, args=(port, logging_path)).start()
            # readloop = get_event_loop()
            # readloop.run_until_complete(reader(port, logging_path))
            log.info('controller returned from Thread')
        
        # backend closed the connection
        elif opcode == 'close':
            # readloop = get_event_loop()
            # readloop.stop()
            # readloop.close()
            # readloop = None
            global stop_reader
            stop_reader = True
        
        # raceid updated from backend
        elif opcode == 'raceid':
            global raceid
            raceid = event['raceid']
        
        # browser wants to know if we're connected to time machine
        elif opcode == 'is_connected':
            await websocket.send(dumps({'opcode': 'connection_status', 'connected': connected}))

        # browser wants to know available com ports
        elif opcode == 'get_comports':
            # preprocess com devices
            cp = comports()
            comdevices = {}
            # note this loop will pick up some with hwaddr = 000000000000, which should be ignored as these are "incoming"
            # adapted from https://stackoverflow.com/a/71024996/799921, https://inthehand.com/2020/11/22/bluetooth-virtual-com-ports/
            for c in cp:
                hwidparts = c.hwid.split('\\')[2]
                hwidfields = hwidparts.split('&')[3]
                hwaddr = hwidfields.split('_')[0]
                if hwaddr != '000000000000':
                    comdevices[hwaddr] = c.device
            
            btdevices = event['bluetoothdevices']
            the_devices = {}
            for bttype in btdevices:
                the_devices.setdefault(bttype, [])
                devices = btdevices[bttype]
                for device in devices:
                    # check if device is in comports
                    if device['hwaddr'] in comdevices:
                        the_devices[bttype].append({'id': comdevices[device['hwaddr']], 'text': device['name']})
            await websocket.send(dumps({'opcode': 'available_devices', 'devices': the_devices}))

async def main():
    async with serve(controller, host="localhost", port=8081):
        await Future() # run forever
    
if __name__ == "__main__":
    try:
        run(main())
    except KeyboardInterrupt:
        log.info('tm-reader exiting')