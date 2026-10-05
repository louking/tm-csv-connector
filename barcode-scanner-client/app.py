# standard
from sys import stdout
from asyncio import run, Future, Protocol, sleep, get_event_loop, new_event_loop, set_event_loop
from threading import Thread
from json import loads, dumps
from logging import basicConfig, getLogger, INFO, DEBUG, StreamHandler, Formatter, LoggerAdapter
from logging.handlers import TimedRotatingFileHandler
from requests import post
from requests import codes
from re import split as resplit
from traceback import format_exception_only
import ctypes
from ctypes import wintypes

# pypi
from websockets import connect, ConnectionClosed
from websockets.server import serve
from serial_asyncio import create_serial_connection
from serial.tools.list_ports import comports

class ReaderClosed(Exception): pass
class LinkLost(Exception): pass

basicConfig(
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    level=DEBUG,
)

log = getLogger('barcode-scanner')
# log.setLevel(DEBUG)
# handler = StreamHandler(stdout)
# handler.setLevel(DEBUG)
# formatter = Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
# handler.setFormatter(formatter)
# log.addHandler(handler)

# these should be configurable
getLogger('websockets.client').setLevel(INFO)
getLogger('websockets.server').setLevel(INFO)

backenduri = 'ws://tm.localhost:8080/barcode_scanner'
backendpost = 'http://tm.localhost:8080/_postbib'

# connection status is global -- is there any way to get a class status from an async protocol?
connected = False

# stop_reader flag
stop_reader = False

# queue messages from input protocol for sending to backend
queued_msgs = []

# save latest raceid
raceid = 0

# set when the user explicitly disconnects (stop_reader honored inside reader()), so
# reader_thread() can tell "user clicked disconnect" apart from "link was lost" and
# only auto-retry the latter
user_closed = False

# true while reader_thread() is alive (actively connected or auto-retrying),
# guards against a duplicate 'open' opcode spawning a second thread
reader_thread_running = False

# port reader_thread() opens on each attempt; an 'open' received while auto-retrying
# updates this, so the operator can switch scanners without the loop retrying the old port
reader_port = None

# seconds to wait between auto-reconnect attempts after the link is lost
RECONNECT_WAIT = 5

# Bluetooth link checking -- when a Bluetooth SPP scanner powers off, Windows keeps the
# virtual COM port open and pyserial raises nothing, and when the scanner powers back on
# it does not reconnect to the still-open port. The port has to be closed and reopened.
# See #146
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
    log.warning(f'Bluetooth API not available, scanner link checking disabled: {e}')
    bluetoothapis = None

def port_bt_address(port):
    """get the remote Bluetooth address for a Bluetooth virtual COM port

    HWID format is BTHENUM\\{uuid}_LOCALMFG&...\\...&<MACADDR>_C...; see tm-reader-client get_comports

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
    
    '''read from barcode scanner, adapted from 
    https://pyserial-asyncio.readthedocs.io/en/latest/shortintro.html#reading-data-in-chunks'''
    def connection_made(self, transport):
        self.transport = transport
        self.residual = ''
        global connected
        connected = True
        log.info('barcode scanner serial connection made')
        # with connect(backenduri) as websocket:
        #     await self.send_to_backend(websocket, {'opcode': 'connected'})

    def connection_lost(self, exc: Exception | None) -> None:
        global connected
        connected = False
        log.info(f'barcode scanner serial connection lost: {exc}')
        # with connect(backenduri) as websocket:
        #     await self.send_to_backend(websocket, {'opcode': 'disconnected'})
        
        return super().connection_lost(exc)

    def data_received(self, data):
        data = data.decode()
        log.debug(f'barcode scanner data received: {data}')
        
        # update first part of data with residual
        data = self.residual + data

        # split into separate messages -- scanner default is to append two CR to end of scanned barcode, allow one  
        # need to decode bytes type
        # messages split on CR (e.g., Tera) or LF (e.g., Inateck)
        msgs = resplit(r'\r|\n', data)
        
        # last part is saved for later, may be empty, don't send to back end
        # note the residual may be the only item in msgs
        self.residual = msgs.pop()
        if self.residual:
            log.debug(f'barcode scanner residual: {self.residual}')
        
        # send each scanned bib to the back end
        for msg in msgs:
            # skip empty msg
            if not msg: continue
            
            try:
                log.debug(f'barcode scanner msg processed: {msg}')
                # each msg is a bib number
                queued_msgs.append({'opcode':'scannedbib', 'raceid': raceid, 'bibno': msg})

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
    global stop_reader, user_closed, connected

    log.info(f'barcode scanner async reader started with port {port}')
    readloop = get_event_loop()
    transport, protocol = await create_serial_connection(readloop, InputChunkProtocol, port)
    protocol.set_logging_path(logging_path)

    # only Bluetooth ports with a known remote address can be link checked
    btaddr = port_bt_address(port) if bluetoothapis else None
    if btaddr is None:
        log.info(f'{port} is not a Bluetooth port with a remote address, link checking disabled')
    last_link_check = readloop.time()
    link_down_count = 0
    link_up = None

    try:
        while True:
            if stop_reader:
                log.info('barcode scanner reader stopped')
                stop_reader = False
                user_closed = True
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

            # check the Bluetooth link, debounced so a transient blip doesn't force a reopen
            if btaddr is not None and readloop.time() - last_link_check >= LINK_CHECK_INTERVAL:
                last_link_check = readloop.time()
                this_link_up = bt_link_up(btaddr)
                if this_link_up != link_up:
                    log.info(f'barcode scanner Bluetooth link state: {this_link_up}')
                    link_up = this_link_up
                if this_link_up == False:
                    link_down_count += 1
                    if link_down_count >= LINK_DOWN_COUNT:
                        log.warning('barcode scanner Bluetooth link lost; closing port')
                        transport.close()
                        connected = False
                        raise LinkLost
                else:
                    link_down_count = 0

    except ReaderClosed:
        return

def reader_thread(logging_path):
    """open the barcode scanner port, and keep reopening it if the Bluetooth link is lost

    Runs until the user explicitly disconnects (stop_reader / user_closed), retrying with
    a fixed backoff any time the link is lost or the port can't be opened (e.g., scanner
    switched off). Reopening the port is what re-establishes the Bluetooth link. Each
    attempt opens reader_port, which controller() may change while auto-retrying.

    Args:
        logging_path (str): passed to protocol, currently unused
    """
    global stop_reader, user_closed, reader_thread_running, connected

    log.info(f'in reader_thread')
    readloop = new_event_loop()
    set_event_loop(readloop)

    reader_thread_running = True
    try:
        while True:
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
                log.info('barcode scanner closed by user request')
                break

            if stop_reader:
                # disconnect requested while there was no open port to catch it
                log.info('barcode scanner closed by user request during reconnect wait')
                stop_reader = False
                break

            connected = False
            log.info(f'barcode scanner not connected; retrying in {RECONNECT_WAIT}s')
            run(sleep(RECONNECT_WAIT))

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
        if opcode in ['open', 'close', 'raceid']:
            log.debug(f'websocket received {event}')
        
        # backend opened the connection
        if opcode == 'open':
            global reader_port, raceid
            # open carries the current raceid -- use it, as after a client restart the
            # browser may reconnect and send open without a separate raceid opcode
            if event.get('raceid'):
                raceid = event['raceid']
            if reader_thread_running:
                if event['port'] != reader_port and not connected:
                    log.info(f'auto-retrying; switching port from {reader_port} to {event["port"]}')
                    reader_port = event['port']
                else:
                    log.info('reader_thread already running (connected or auto-retrying); ignoring open')
            else:
                reader_port = event['port']
                logging_path = event['loggingpath']
                readloop_threadid = Thread(target=reader_thread, args=(logging_path,)).start()
                log.info('controller returned from Thread')
        
        # backend closed the connection
        elif opcode == 'close':
            global stop_reader
            stop_reader = True
        
        # raceid updated from backend
        elif opcode == 'raceid':
            raceid = event['raceid']
        
        # browser wants to know if we're connected to barcode scanner
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