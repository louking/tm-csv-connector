# standard
from sys import stdout
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread
from datetime import datetime
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, StreamHandler, Formatter, LoggerAdapter
from logging.handlers import TimedRotatingFileHandler
from requests import post
from requests import codes
from requests import RequestException
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

# backend post timeouts, seconds (connect, read). The read timeout is longer than nginx's default
# 60s proxy_read_timeout, so a hung app gets a 504 from nginx first (#163)
POST_TIMEOUT = (5, 75)

# seconds to wait before retrying a failed post, by attempt; the last is repeated until it succeeds
POST_RETRY_WAITS = [1, 2, 5]

def device_time():
    """local time a device message arrived, to the millisecond, sent with it so the server
    can log it; posts lag arrival by the queue's polling and earlier posts (#157)"""
    return datetime.now().isoformat(timespec='milliseconds')

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
                        queued_msgs.append({'opcode': 'primary', 'raceid': raceid, 'pos': pos, 'time': time,
                                            'device_time': device_time()})
                    elif control == SELECT:
                        bib = int(msg[27:32].decode())
                        queued_msgs.append({'opcode': 'select', 'raceid': raceid, 'pos': pos, 'time': time, 'bibno': bib,
                                            'device_time': device_time()})
            except ValueError:
                log.error(f'could not decode message: {msg}')

    def set_logging_path(self, logging_path):
        self.logging_path = logging_path
        log.error(f'need to set logging path in logger')
        
def send_to_backend(data, attempt=0):
    """send data to backend

    A connection error, timeout, or 5xx (e.g., the app container restarting) may mean the message
    didn't get there, so it's retried. A refusal (4xx, or status other than success) won't succeed
    on retry, so the message is dropped (#163)

    Args:
        data (dict): dict to serialize and send
        attempt (int): number of earlier failed attempts to send this message

    Returns:
        bool: True if done with the message (accepted or dropped), False if it should be retried
    """
    # 'sending to backend' is logged once per message, so the log can be used to count and rebuild them
    if attempt == 0:
        log.debug(f'sending to backend: {data}')
    else:
        log.debug(f'resending to backend (retry {attempt}): {data}')
    try:
        rsp = post(backendpost, json=data, timeout=POST_TIMEOUT)
    except RequestException as e:
        log.error(f'error sending to backend, will retry: {e}')
        return False

    if rsp.status_code >= 500:
        log.error(f'error sending to backend, will retry: status = {rsp.status_code}')
        return False
    if rsp.status_code != codes.ok:
        log.error(f'backend refused message, dropped: status = {rsp.status_code}, message = {data}')
        return True
    try:
        respdata = loads(rsp.text)
    except ValueError:
        log.error(f'backend response not understood, message dropped: response = {rsp.text[:200]}, message = {data}')
        return True
    if respdata.get('status') != 'success':
        log.error(f'backend refused message, dropped: response = {respdata.get("error")}, message = {data}')
    return True

async def reader(port, logging_path):
    log.info(f'time machine async reader started with port {port}')
    readloop = get_event_loop()
    transport, protocol = await create_serial_connection(readloop, InputChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    # retry state for the message at the head of queued_msgs
    post_attempt = 0
    next_post_time = readloop.time()

    try:
        while True:
            global stop_reader
            if stop_reader:
                log.info('time machine reader stopped')
                stop_reader = False
                transport.close()
                raise ReaderClosed
            
            # reading isn't paused (unlike the pyserial-asyncio chunk example), so data_received() runs and
            # stamps device_time as data arrives during this sleep; data arriving during a blocking post
            # is read right after it (#157)
            await sleep(0.3)
            
            # send queued messages oldest first, one at a time to keep them in order. a message stays at
            # the head of the queue until the backend accepts or refuses it, and the retry wait doesn't
            # block this loop, so reading and stop_reader still work while the backend is down (#163)
            global queued_msgs
            while queued_msgs and readloop.time() >= next_post_time:
                if send_to_backend(queued_msgs[0], post_attempt):
                    queued_msgs.pop(0)
                    post_attempt = 0
                else:
                    post_attempt += 1
                    next_post_time = readloop.time() + POST_RETRY_WAITS[min(post_attempt, len(POST_RETRY_WAITS)) - 1]
                    log.info(f'{len(queued_msgs)} message(s) waiting to send to backend')

    
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
            global raceid
            # open carries the current raceid -- use it, as after a client restart the
            # browser may reconnect and send open without a separate raceid opcode
            if event.get('raceid'):
                raceid = event['raceid']
            port = event['port']
            logging_path = event['loggingpath']
            readloop_threadid = Thread(target=reader_thread, args=(port, logging_path), daemon=True).start()
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