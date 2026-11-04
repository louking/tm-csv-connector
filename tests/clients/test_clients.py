'''tm-reader-client and barcode-scanner-client: reading and splitting device bytes, queueing, posting
in order with retries (#163), the TM open timeout (#154), and the reconnect loop and status (#146, #151)
'''
# standard
from asyncio import run
from threading import Event, Thread
from json import dumps, loads
from time import sleep

# pypi
import pytest

# homegrown
from conftest import wait_until, Response, FakeBackend, connection_refused, LoopReader

# device bytes, from the client logs
TM_RESULT = b'\x1711 246 0246 01:03:01.03 \r\n'
TM_KEYPAD = b'\x1411 001 0001 00:00:04.24   00102\r\n'

def tm_result(pos, time):
    return f'\x1711 {pos:03d} {pos:04d} {time} \r\n'.encode('latin-1')

def scan(bib):
    return f'{bib}\r\r'.encode()

def without_times(msgs):
    """messages without device_time, which varies"""
    return [{k: v for k, v in m.items() if k != 'device_time'} for m in msgs]

class Transport:
    serial = None

# reading and splitting

def feed(module, *pieces):
    protocol = module.InputChunkProtocol()
    protocol.connection_made(Transport())
    for piece in pieces:
        protocol.data_received(piece)
    return protocol

def test_tm_messages(tm):
    tm.raceid = 12
    feed(tm, TM_RESULT, TM_KEYPAD)
    assert without_times(tm.queued_msgs) == [
        {'opcode': 'primary', 'raceid': 12, 'pos': 246, 'time': '01:03:01.03'},
        {'opcode': 'select', 'raceid': 12, 'pos': 1, 'time': '00:00:04.24', 'bibno': 102},
    ]
    assert all(len(m['device_time']) == len('2026-11-01T09:20:01.512') for m in tm.queued_msgs)

def test_tm_message_in_pieces(tm):
    """the Time Machine link often delivers a message in 2-3 reads (#157)"""
    protocol = feed(tm, TM_RESULT[:5], TM_RESULT[5:20])
    assert tm.queued_msgs == [] and protocol.residual == TM_RESULT[:20]
    protocol.data_received(TM_RESULT[20:] + TM_KEYPAD[:3])
    assert [m['pos'] for m in tm.queued_msgs] == [246]
    protocol.data_received(TM_KEYPAD[3:])
    assert [m['pos'] for m in tm.queued_msgs] == [246, 1]

def test_tm_other_messages_ignored(tm):
    feed(tm, b'\x1211 some other message\r\n', b'\x17garbled\r\n', TM_RESULT)
    assert [m['pos'] for m in tm.queued_msgs] == [246]

def test_scans(scanner):
    scanner.raceid = 12
    feed(scanner, scan('2164'), b'0042\n', b'0000\r\r')
    assert without_times(scanner.queued_msgs) == [
        {'opcode': 'scannedbib', 'raceid': 12, 'bibno': '2164'},
        {'opcode': 'scannedbib', 'raceid': 12, 'bibno': '0042'},
        {'opcode': 'scannedbib', 'raceid': 12, 'bibno': '0000'},
    ]

def test_scan_in_pieces(scanner):
    protocol = feed(scanner, b'21', b'64')
    assert scanner.queued_msgs == [] and protocol.residual == '2164'
    protocol.data_received(b'\r\r33')
    assert [m['bibno'] for m in scanner.queued_msgs] == ['2164']

# send_to_backend

@pytest.mark.parametrize('client', ['tm', 'scanner'])
@pytest.mark.parametrize('outcome, done', [
    (Response(200, {'status': 'success'}), True),
    # refusals won't succeed on retry, so the message is dropped
    (Response(200, {'status': 'fail', 'error': 'IntegrityError'}), True),
    (Response(404, text='not found'), True),
    (Response(200, text='<html>'), True),
    # these may not have reached the app, so they're retried
    (Response(502, text='bad gateway'), False),
    (Response(504, text='gateway timeout'), False),
    (connection_refused(), False),
])
def test_send_to_backend(request, client, outcome, done):
    module = request.getfixturevalue(client)
    backend = FakeBackend(module, [outcome])
    assert module.send_to_backend({'opcode': 'x'}) is done
    assert backend.posts == [{'opcode': 'x'}]

# reading and posting on a loop:// port

def test_tm_reader_posts_in_order(tm):
    tm.raceid = 12
    backend = FakeBackend(tm)
    reader = LoopReader(tm, 'connection_for_serial')
    try:
        # connection_made() runs just after the port opens
        assert wait_until(lambda: tm.connected)
        for pos in range(1, 21):
            msg = tm_result(pos, f'00:20:{pos:02d}.00')
            # some messages arrive in pieces, as from the real device
            if pos % 3 == 0:
                reader.write(msg[:9])
                sleep(0.05)
                reader.write(msg[9:])
            else:
                reader.write(msg)
        assert wait_until(lambda: len(backend.accepted) == 20)
    finally:
        reader.stop()
    assert [m['pos'] for m in backend.accepted] == list(range(1, 21))
    assert all(m['raceid'] == 12 for m in backend.accepted)
    assert not tm.connected

def test_scanner_reader_posts_in_order(scanner):
    scanner.raceid = 12
    backend = FakeBackend(scanner)
    reader = LoopReader(scanner, 'create_serial_connection')
    try:
        for bib in range(100, 120):
            reader.write(scan(bib))
        assert wait_until(lambda: len(backend.accepted) == 20)
    finally:
        reader.stop()
    assert [m['bibno'] for m in backend.accepted] == [str(b) for b in range(100, 120)]

@pytest.mark.parametrize('client, wrap_name, message, key', [
    ('tm', 'connection_for_serial', lambda i: tm_result(i, f'00:20:{i:02d}.00'), 'pos'),
    ('scanner', 'create_serial_connection', lambda i: scan(i), 'bibno'),
])
def test_retries_keep_order(request, client, wrap_name, message, key):
    """a backend that's down holds the queue in order; refused messages are dropped (#163)"""
    module = request.getfixturevalue(client)
    module.raceid = 12
    backend = FakeBackend(module, [connection_refused(), Response(502, text=''), Response(503, text=''),
                                   Response(200, {'status': 'fail', 'error': 'refused'})])
    reader = LoopReader(module, wrap_name)
    try:
        for i in range(1, 6):
            reader.write(message(i))
        assert wait_until(lambda: len(backend.accepted) == 4)
        # the device is still read while posts are retried
        reader.write(message(6))
        assert wait_until(lambda: len(backend.accepted) == 5)
    finally:
        reader.stop()
    # message 1 failed three times and was then refused; the rest were sent once each, in order
    assert [str(m[key]) for m in backend.posts] == ['1', '1', '1', '1', '2', '3', '4', '5', '6']
    assert [str(m[key]) for m in backend.accepted] == ['2', '3', '4', '5', '6']

def test_messages_kept_across_disconnect(scanner):
    """messages still queued when the operator disconnects are sent after the next Connect"""
    backend = FakeBackend(scanner, [connection_refused()] * 100)
    reader = LoopReader(scanner, 'create_serial_connection')
    reader.write(scan(5))
    assert wait_until(lambda: backend.posts)
    reader.stop()
    assert [m['bibno'] for m in scanner.queued_msgs] == ['5']
    backend.outcomes = []
    reader = LoopReader(scanner, 'create_serial_connection')
    try:
        assert wait_until(lambda: backend.accepted)
    finally:
        reader.stop()
    assert [m['bibno'] for m in backend.accepted] == ['5']

# tm-reader-client open timeout (#154)

class FakeSerial:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

def test_hung_open_gives_up(tm):
    tm.OPEN_TIMEOUT = 0.3
    release = Event()
    opened = []

    def hanging_open(port):
        release.wait(10)
        ser = FakeSerial()
        opened.append(ser)
        return ser

    tm.serial_for_url = hanging_open
    for _ in range(tm.MAX_HUNG_OPENS):
        with pytest.raises(tm.OpenTimeout, match='gave up'):
            run(tm.open_port('COM9'))
    # with too many still hung, attempts stop without opening another
    with pytest.raises(tm.OpenTimeout, match='earlier opens are still hung'):
        run(tm.open_port('COM9'))
    # an open that completes after it was given up on closes the port, so it doesn't hold it
    release.set()
    assert wait_until(lambda: len(opened) == tm.MAX_HUNG_OPENS and all(s.closed for s in opened))
    assert wait_until(lambda: all(o.done.is_set() for o in tm.hung_opens))
    tm.serial_for_url = lambda port: FakeSerial()
    assert not run(tm.open_port('COM9')).closed

def test_open_stopped_by_disconnect(tm):
    tm.serial_for_url = lambda port: Event().wait(10)
    Thread(target=lambda: (sleep(0.3), setattr(tm, 'stop_reader', True)), daemon=True).start()
    with pytest.raises(tm.OpenTimeout, match='user disconnected'):
        run(tm.open_port('COM9'))

def test_open_error_raised(tm):
    def failing_open(port):
        raise OSError('semaphore timeout')
    tm.serial_for_url = failing_open
    with pytest.raises(OSError, match='semaphore timeout'):
        run(tm.open_port('COM9'))

# reconnect loop and status, through the WebSocket controller

class FakeWebSocket:
    """the browser's side of a client's WebSocket"""
    def __init__(self, *events):
        self.events = [dumps(e) for e in events]
        self.sent = []

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)

    async def send(self, message):
        self.sent.append(loads(message))

def control(module, *events):
    ws = FakeWebSocket(*events)
    run(module.controller(ws))
    return ws.sent

def status(module):
    reply = control(module, {'opcode': 'is_connected'})[0]
    # the TM reader's socket also carries available_devices, so its reply has an opcode (#154)
    opcode = reply.pop('opcode', None)
    assert opcode == ('connection_status' if hasattr(module, 'OPEN_TIMEOUT') else None)
    return reply

@pytest.mark.parametrize('client', ['tm', 'scanner'])
def test_reconnect_loop(request, client):
    """a port that won't open is retried, an open with another port switches to it, and Stop ends it"""
    module = request.getfixturevalue(client)
    FakeBackend(module)
    assert status(module) == {'connected': False, 'status': 'disconnected', 'port': None}
    control(module, {'opcode': 'open', 'port': 'COM250', 'loggingpath': None, 'raceid': 7})
    # open carries the race, for a client that restarted (#147)
    assert module.raceid == 7
    assert wait_until(lambda: status(module)['status'] == 'reconnecting')
    assert status(module)['port'] == 'COM250'
    # a second open for the same port doesn't start another thread
    control(module, {'opcode': 'open', 'port': 'COM250', 'loggingpath': None})
    control(module, {'opcode': 'open', 'port': 'loop://', 'loggingpath': None})
    assert wait_until(lambda: status(module)['status'] == 'connected', timeout=10)
    assert status(module) == {'connected': True, 'status': 'connected', 'port': 'loop://'}
    control(module, {'opcode': 'close'})
    assert wait_until(lambda: status(module)['status'] == 'disconnected')
    assert not module.reader_thread_running

@pytest.mark.parametrize('client', ['tm', 'scanner'])
def test_stop_while_reconnecting(request, client):
    module = request.getfixturevalue(client)
    control(module, {'opcode': 'open', 'port': 'COM250', 'loggingpath': None, 'raceid': 7})
    assert wait_until(lambda: status(module)['status'] == 'reconnecting')
    control(module, {'opcode': 'close'})
    assert wait_until(lambda: status(module)['status'] == 'disconnected')
    # a close with nothing running is ignored, so it can't stop the next connect
    control(module, {'opcode': 'close'})
    assert not module.stop_reader

@pytest.mark.parametrize('client', ['tm', 'scanner'])
def test_raceid_opcode(request, client):
    module = request.getfixturevalue(client)
    control(module, {'opcode': 'raceid', 'raceid': 9})
    assert module.raceid == 9
