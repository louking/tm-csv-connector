# standard
from sys import stdout
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread, Lock, Event
from datetime import datetime
from time import sleep as blocking_sleep
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, StreamHandler, Formatter, LoggerAdapter
from logging.handlers import TimedRotatingFileHandler
from requests import post
from requests import codes
from requests import RequestException
from serial.tools.list_ports import comports
from traceback import format_exception_only
import ctypes
from ctypes import wintypes

# pypi
from websockets import connect, ConnectionClosed
from websockets.server import serve
from serial import serial_for_url
from serial_asyncio import connection_for_serial

class ReaderClosed(Exception): pass
class LinkLost(Exception): pass
class OpenTimeout(Exception): pass

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

# set when the user explicitly disconnects (stop_reader honored inside reader()), so
# reader_thread() can tell "user clicked disconnect" apart from "link was lost" and
# only auto-retry the latter (#154, same as barcode-scanner-client #146)
user_closed = False

# true while reader_thread() is alive (actively connected or auto-retrying),
# guards against a duplicate 'open' opcode spawning a second thread
reader_thread_running = False

# true once reader_thread() has had an attempt fail or a connection drop, so client_status()
# can tell a first connect attempt ('connecting') apart from auto-retrying ('reconnecting')
retrying = False

# port reader_thread() opens on each attempt; an 'open' received while auto-retrying
# updates this, so the operator can switch ports without the loop retrying the old one
reader_port = None

# seconds to wait between auto-reconnect attempts after the link is lost
RECONNECT_WAIT = 5

# seconds to wait for the serial port to open before giving up on the attempt. A good Bluetooth
# open has taken 3-5s, but one has also hung with no error until the Time Machine was power-cycled (#154)
OPEN_TIMEOUT = 15

# opens still hung after their attempt gave up, see PortOpener. Each is a thread blocked in the
# open, so stop retrying when there are this many
MAX_HUNG_OPENS = 3
hung_opens = []

# Bluetooth link checking -- when a Bluetooth SPP device powers off, Windows keeps the
# virtual COM port open and pyserial raises nothing. See barcode-scanner-client, #146
LINK_CHECK_INTERVAL = 2     # seconds between link checks
LINK_DOWN_COUNT = 3         # consecutive "down" checks before the link is declared lost

class SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wintypes.WORD) for n in ('wYear', 'wMonth', 'wDayOfWeek', 'wDay', 'wHour', 'wMinute', 'wSecond', 'wMilliseconds')]

class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('Address', ctypes.c_ulonglong),
        ('ulClassofDevice', wintypes.ULONG),
        ('fConnected', wintypes.BOOL),
        ('fRemembered', wintypes.BOOL),
        ('fAuthenticated', wintypes.BOOL),
        ('stLastSeen', SYSTEMTIME),
        ('stLastUsed', SYSTEMTIME),
        ('szName', wintypes.WCHAR * 248),
    ]

try:
    bluetoothapis = ctypes.WinDLL('BluetoothApis.dll')
except (AttributeError, OSError) as e:
    log.warning(f'Bluetooth API not available, Time Machine link checking disabled: {e}')
    bluetoothapis = None

def port_bt_address(port):
    """get the remote Bluetooth address for a Bluetooth virtual COM port

    HWID format is BTHENUM\\{uuid}_LOCALMFG&...\\...&<MACADDR>_C...; see get_comports

    Args:
        port (str): COM port name, e.g., COM3

    Returns:
        int | None: address for BluetoothGetDeviceInfo, or None if not a Bluetooth port with a remote address
    """
    for c in comports():
        if c.device != port:
            continue
        try:
            hwaddr = c.hwid.split('\\')[2].split('&')[3].split('_')[0]
            if hwaddr != '000000000000':
                return int(hwaddr, 16)
        except (IndexError, ValueError):
            pass
    return None

def bt_link_up(address):
    """check whether Windows reports a live Bluetooth link to the device

    Args:
        address (int): Bluetooth address from port_bt_address()

    Returns:
        bool | None: link state, or None if it couldn't be determined
    """
    info = BLUETOOTH_DEVICE_INFO()
    info.dwSize = ctypes.sizeof(info)
    info.Address = address
    rc = bluetoothapis.BluetoothGetDeviceInfo(None, ctypes.byref(info))
    if rc != 0:
        return None
    # fConnected is nonzero (e.g., 32), not necessarily 1, when connected
    return info.fConnected != 0

class PortOpener:
    """open a serial port in its own thread, so an open that hangs can be given up on (#154)

    The thread is a daemon, not an executor thread, since asyncio.run() waits for executor threads
    when it finishes. If an open completes after it was given up on, the port is closed, so it
    doesn't hold the port against later attempts.

    Args:
        port (str): port to open
    """
    def __init__(self, port):
        self.port = port
        self.lock = Lock()
        self.done = Event()
        self.serial = None
        self.error = None
        self.abandoned = False
        Thread(target=self._open, daemon=True).start()

    def _open(self):
        try:
            ser = serial_for_url(self.port)
        except Exception as e:
            self.error = e
            self.done.set()
            return
        with self.lock:
            if self.abandoned:
                log.info(f'{self.port} open completed after it was given up on; closing it')
                ser.close()
            else:
                self.serial = ser
        self.done.set()

    def abandon(self):
        """give up on the open; returns False if it had already completed, so the caller can use it"""
        with self.lock:
            if self.serial is not None:
                return False
            self.abandoned = True
            return True

async def open_port(port):
    """open port, giving up after OPEN_TIMEOUT or when the user disconnects

    Args:
        port (str): port to open

    Raises:
        OpenTimeout: the open didn't complete in time, or stop_reader was set while waiting
        Exception: whatever the open raised

    Returns:
        Serial: the open port
    """
    global hung_opens
    hung_opens = [o for o in hung_opens if not o.done.is_set()]
    if len(hung_opens) >= MAX_HUNG_OPENS:
        raise OpenTimeout(f'{len(hung_opens)} earlier opens are still hung -- power-cycle the Time Machine, '
                          f'or restart the TmReader service')

    opener = PortOpener(port)
    loop = get_event_loop()
    start = loop.time()
    while not opener.done.is_set():
        waited = loop.time() - start
        if stop_reader or waited >= OPEN_TIMEOUT:
            if opener.abandon():
                hung_opens.append(opener)
                raise OpenTimeout(f'gave up after {waited:.1f}s' + (' (user disconnected)' if stop_reader else ''))
            break
        await sleep(0.1)

    if opener.error:
        raise opener.error
    return opener.serial

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
    global stop_reader, user_closed, connected

    log.info(f'time machine async reader started with port {port}')
    readloop = get_event_loop()
    # a hung open raises OpenTimeout instead of blocking forever (#154)
    serial_instance = await open_port(port)
    transport, protocol = await connection_for_serial(readloop, InputChunkProtocol, serial_instance)
    protocol.set_logging_path(logging_path)

    # only Bluetooth ports with a known remote address can be link checked
    btaddr = port_bt_address(port) if bluetoothapis else None
    if btaddr is None:
        log.info(f'{port} is not a Bluetooth port with a remote address, link checking disabled')
    last_link_check = readloop.time()
    link_down_count = 0
    link_up = None

    # retry state for the message at the head of queued_msgs
    post_attempt = 0
    next_post_time = readloop.time()

    try:
        while True:
            if stop_reader:
                log.info('time machine reader stopped')
                stop_reader = False
                user_closed = True
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

            # check the Bluetooth link, debounced so a transient blip doesn't force a reopen
            if btaddr is not None and readloop.time() - last_link_check >= LINK_CHECK_INTERVAL:
                last_link_check = readloop.time()
                this_link_up = bt_link_up(btaddr)
                if this_link_up != link_up:
                    log.info(f'time machine Bluetooth link state: {this_link_up}')
                    link_up = this_link_up
                if this_link_up == False:
                    link_down_count += 1
                    if link_down_count >= LINK_DOWN_COUNT:
                        log.warning('time machine Bluetooth link lost; closing port')
                        transport.close()
                        connected = False
                        raise LinkLost
                else:
                    link_down_count = 0

    except ReaderClosed:
        return

def client_status():
    """connection status for the browser, see #151, #154

    Returns:
        str: 'connected', 'connecting' (first attempt in progress), 'reconnecting' (auto-retrying
            after a failed attempt or lost link), or 'disconnected' (not running, e.g., user disconnected)
    """
    if connected:
        return 'connected'
    if reader_thread_running:
        return 'reconnecting' if retrying else 'connecting'
    return 'disconnected'

def wait_for_retry():
    """wait RECONNECT_WAIT seconds before the next open attempt, returning early if the user disconnects"""
    for _ in range(RECONNECT_WAIT * 10):
        if stop_reader:
            return
        blocking_sleep(0.1)

def reader_thread(logging_path):
    """open the Time Machine port, and keep reopening it if the open fails or hangs, or the link is lost

    Runs until the user explicitly disconnects (stop_reader / user_closed), retrying with a fixed
    backoff, as barcode-scanner-client does (#146, #154). Each attempt opens reader_port, which
    controller() may change while auto-retrying.

    Args:
        logging_path (str): passed to protocol, currently unused
    """
    global stop_reader, user_closed, reader_thread_running, connected, retrying

    log.info(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)

    reader_thread_running = True
    retrying = False
    try:
        while True:
            if stop_reader:
                # disconnect requested while there was no open port to catch it
                log.info('time machine closed by user request while reconnecting')
                stop_reader = False
                break

            user_closed = False
            port = reader_port
            try:
                run(reader(port, logging_path))

            except LinkLost:
                pass

            except Exception as e:
                exc = ''.join(format_exception_only(type(e), e))
                log.error(f'exception occurred opening {port} - {exc}')

            if user_closed:
                log.info('time machine closed by user request')
                break

            connected = False
            retrying = True
            if not stop_reader:
                log.info(f'time machine not connected; retrying in {RECONNECT_WAIT}s')
                wait_for_retry()

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
        if opcode in ['open', 'close', 'raceid', 'get_comports']:
            log.debug(f'websocket received {event}')
        
        # backend opened the connection
        if opcode == 'open':
            global reader_port, raceid, stop_reader
            # open carries the current raceid -- use it, as after a client restart the
            # browser may reconnect and send open without a separate raceid opcode
            if event.get('raceid'):
                raceid = event['raceid']
            # one reader thread at a time; before #154 each Connect while an open hung started another
            if reader_thread_running:
                if event['port'] != reader_port and not connected:
                    log.info(f'auto-retrying; switching port from {reader_port} to {event["port"]}')
                    reader_port = event['port']
                else:
                    log.info('reader_thread already running (connected or auto-retrying); ignoring open')
            else:
                # clear any stale close sent while nothing was running, so it can't stop the new thread
                stop_reader = False
                reader_port = event['port']
                logging_path = event['loggingpath']
                readloop_threadid = Thread(target=reader_thread, args=(logging_path,), daemon=True).start()
                log.info('controller returned from Thread')

        # backend closed the connection
        # (also cancels auto-retrying, #154)
        elif opcode == 'close':
            if reader_thread_running:
                stop_reader = True

        # raceid updated from backend
        elif opcode == 'raceid':
            raceid = event['raceid']

        # browser wants to know if we're connected to time machine
        # port lets the browser tell whether Connect would switch ports while connecting/reconnecting
        elif opcode == 'is_connected':
            await websocket.send(dumps({
                'opcode': 'connection_status',
                'connected': connected,
                'status': client_status(),
                'port': reader_port if reader_thread_running else None,
            }))

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