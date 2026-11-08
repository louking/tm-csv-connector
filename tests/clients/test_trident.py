'''trident-reader-client: posting chip reads, status debounce, the reconnect loop, and close (#167)

The chip reader is a fake: a TCP server on localhost, in its own thread. The real reader's network
interface is plain TCP too, so telnetlib3 sees no telnet negotiation from either. ping3 is replaced,
so each test sets what a ping returns.
'''
# standard
from asyncio import new_event_loop, start_server, run_coroutine_threadsafe, run, sleep as async_sleep
from functools import partial
from threading import Thread
from time import monotonic

# pypi
import pytest

# homegrown
from conftest import wait_until, Response, control

GUNTIME = 'abA000002607060010300000'

def chipread(tag, counter):
    """a chip read line, in the layout trident.tridentread2obj() reads"""
    return f'aaA1{tag:012d}{counter:04d}261108093015' + '1E00LR3C'

class Backend:
    """stands in for requests.post: chip reads to /_livechipreads, status to /_chipreaderstatus"""
    def __init__(self, module):
        self.reads = []
        self.statuses = []
        module.post = self.post

    def post(self, url, json=None):
        if url.endswith('/_livechipreads'):
            self.reads.append(json)
        elif url.endswith('/_chipreaderstatus'):
            self.statuses.append((monotonic(), json['status']))
        else:
            raise AssertionError(f'unexpected post to {url}')
        return Response(200, {'status': 'success'})

    def lines(self):
        """chip read lines posted, in order"""
        return [line for r in self.reads for line in r['data'].split('\r\n')]

    def status_list(self):
        return [s for _, s in self.statuses]

class Ping:
    """stands in for ping3.ping: a float is a reply, None no reply, False an unreachable network"""
    def __init__(self, module, reply=0.001):
        self.reply = reply
        module.ping = self.ping

    def ping(self, ipaddr, timeout=None):
        return self.reply

class FakeReader:
    """the chip reader's network interface: accepts connections on localhost, until stopped"""
    def __init__(self, port=0):
        self.loop = new_event_loop()
        self.writers = []
        self.thread = Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.server = self._call(self._start(port))
        self.port = self.server.sockets[0].getsockname()[1]

    def _call(self, coro):
        return run_coroutine_threadsafe(coro, self.loop).result(timeout=5)

    async def _start(self, port):
        return await start_server(self._accept, '127.0.0.1', port)

    async def _accept(self, reader, writer):
        self.writers.append(writer)
        # hold the connection open until the client or the test closes it
        await reader.read()

    def send(self, text):
        async def write():
            self.writers[-1].write(text.encode())
            await self.writers[-1].drain()
        self._call(write())

    def drop(self):
        """close the open connection, as the reader does when it restarts"""
        async def close():
            self.writers[-1].close()
        self._call(close())

    def stop(self):
        async def stop():
            self.server.close()
            for w in self.writers:
                w.close()
        self._call(stop())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)

@pytest.fixture
def chipreader():
    reader = FakeReader()
    yield reader
    reader.stop()

@pytest.fixture
def client(trident):
    """the client module, with fast waits; stops its reader thread at the end"""
    # skip telnetlib3's wait for telnet negotiation, which the reader never sends (3s by default)
    trident.open_connection = partial(trident.open_connection, connect_maxwait=0.05)
    # shell() waits about 1s between reads; a tenth of that keeps the tests quick
    async def fast_sleep(secs):
        await async_sleep(secs / 10)
    trident.sleep = fast_sleep
    yield trident
    if trident.reader_thread_running:
        control(trident, {'opcode': 'close'})
        assert wait_until(lambda: not trident.reader_thread_running, timeout=10)

def open_reader(module, port, raceid=7):
    control(module, {'opcode': 'open', 'ipaddr': '127.0.0.1', 'fport': port, 'loggingpath': None, 'raceid': raceid})

def status(module):
    return control(module, {'opcode': 'is_connected'})[0]

def test_reads_posted(client, chipreader):
    """lines are posted as they arrive, with the race; a partial line waits for the rest"""
    backend = Backend(client)
    Ping(client)
    open_reader(client, chipreader.port)
    assert wait_until(lambda: status(client)['status'] == 'connected')
    chipreader.send(chipread(1, 1) + '\r\n' + chipread(2, 2) + '\r\n' + GUNTIME[:10])
    assert wait_until(lambda: len(backend.lines()) == 2)
    chipreader.send(GUNTIME[10:] + '\r\n')
    assert wait_until(lambda: len(backend.lines()) == 3)
    assert backend.lines() == [chipread(1, 1), chipread(2, 2), GUNTIME]
    assert all(r['raceid'] == 7 for r in backend.reads)
    # a raceid opcode changes the race for later reads
    control(client, {'opcode': 'raceid', 'raceid': 8})
    chipreader.send(chipread(3, 3) + '\r\n')
    assert wait_until(lambda: len(backend.lines()) == 4)
    assert backend.reads[-1]['raceid'] == 8

def test_status_debounce(client):
    """a status is reported only after it's seen STATUS_DEBOUNCE_COUNT times in a row"""
    backend = Backend(client)
    assert client.STATUS_DEBOUNCE_COUNT == 3
    for _ in range(2):
        client.check_update_status('connected')
    assert backend.status_list() == []
    client.check_update_status('connected')
    assert backend.status_list() == ['connected'] and client.detailedstatus == 'connected'
    # a blip that doesn't repeat isn't reported, and seeing the current status starts the count again
    client.check_update_status('no-response')
    client.check_update_status('no-response')
    client.check_update_status('connected')
    client.check_update_status('no-response')
    client.check_update_status('network-unreachable')
    client.check_update_status('no-response')
    assert backend.status_list() == ['connected']
    client.check_update_status('no-response')
    client.check_update_status('no-response')
    assert backend.status_list() == ['connected', 'no-response']
    # a connection that closed is reported at once
    client.check_update_status('disconnected', immediate=True)
    assert backend.status_list() == ['connected', 'no-response', 'disconnected']

def test_ping_status(client, chipreader):
    """with no data from the reader, the ping result sets the status"""
    backend = Backend(client)
    ping = Ping(client)
    open_reader(client, chipreader.port)
    assert wait_until(lambda: backend.status_list() == ['connected'])
    ping.reply = False
    assert wait_until(lambda: backend.status_list()[-1:] == ['network-unreachable'])
    ping.reply = None
    assert wait_until(lambda: backend.status_list()[-1:] == ['no-response'])
    # status is about the network, the socket is still open
    assert status(client) == {'connected': True, 'detailedstatus': 'no-response', 'status': 'connected'}
    ping.reply = 0.001
    assert wait_until(lambda: backend.status_list()[-1:] == ['connected'])
    assert backend.status_list() == ['connected', 'network-unreachable', 'no-response', 'connected']

def test_reconnect_after_drop(client, chipreader):
    """a connection the reader closes is reported at once, and the client reconnects by itself"""
    client.RECONNECT_WAIT = 1
    backend = Backend(client)
    Ping(client)
    open_reader(client, chipreader.port)
    assert wait_until(lambda: backend.status_list() == ['connected'])
    # a second open while connected doesn't start another connection
    open_reader(client, chipreader.port)
    dropped = monotonic()
    chipreader.drop()
    assert wait_until(lambda: backend.status_list()[-1:] == ['disconnected'])
    # posted when the drop is seen, without waiting for repeats
    assert backend.statuses[-1][0] - dropped < 1
    assert wait_until(lambda: status(client)['status'] == 'reconnecting')
    assert wait_until(lambda: len(chipreader.writers) == 2 and status(client)['status'] == 'connected', timeout=10)
    assert wait_until(lambda: backend.status_list()[-1:] == ['connected'])
    chipreader.send(chipread(4, 4) + '\r\n')
    assert wait_until(lambda: backend.lines() == [chipread(4, 4)])
    # Disconnect stops it for good
    control(client, {'opcode': 'close'})
    assert wait_until(lambda: status(client)['status'] == 'disconnected')
    assert not client.reader_thread_running and client.user_closed
    assert backend.status_list() == ['connected', 'disconnected', 'connected', 'disconnected']
    assert len(chipreader.writers) == 2

def test_reader_not_up_yet(client):
    """a reader that isn't listening yet (still powering on) is retried until it is"""
    client.RECONNECT_WAIT = 1
    Backend(client)
    Ping(client)
    # a port nothing listens on, for now
    reader = FakeReader()
    port = reader.port
    reader.stop()
    assert status(client)['status'] == 'disconnected'
    open_reader(client, port)
    assert wait_until(lambda: status(client)['status'] == 'reconnecting', timeout=10)
    reader = FakeReader(port)
    try:
        assert wait_until(lambda: status(client)['status'] == 'connected', timeout=15)
    finally:
        control(client, {'opcode': 'close'})
        assert wait_until(lambda: not client.reader_thread_running, timeout=10)
        reader.stop()

def test_close_while_reconnecting(client):
    """Stop Reconnecting ends the retry loop; a close with nothing running is ignored"""
    client.RECONNECT_WAIT = 5
    Backend(client)
    reader = FakeReader()
    port = reader.port
    reader.stop()
    open_reader(client, port)
    assert wait_until(lambda: status(client)['status'] == 'reconnecting', timeout=10)
    closed = monotonic()
    control(client, {'opcode': 'close'})
    assert wait_until(lambda: status(client)['status'] == 'disconnected', timeout=10)
    # well before the 5s wait would have ended, unless it caught a connect attempt
    assert monotonic() - closed < 4
    control(client, {'opcode': 'close'})
    assert not client.stop_reader

class BrokenReader:
    """a telnet reader whose read fails as Windows' does when the network drops (#151)"""
    def __init__(self):
        self.eof_fed = False

    async def read(self, n):
        raise OSError(121, 'The semaphore timeout period has expired')

    def at_eof(self):
        return False

    def feed_eof(self):
        self.eof_fed = True

class BrokenWriter:
    def __init__(self):
        self.connection_closed = False
        self.transport = self

    def get_extra_info(self, name):
        return ('10.0.0.1', 10001)

    def close(self):
        self.connection_closed = True

def test_network_error_in_read(client):
    """an OSError from a read ends shell() cleanly: connected is cleared and disconnected is reported,
    so the reconnect loop takes over (#151)"""
    backend = Backend(client)
    client.connected = True
    client.detailedstatus = 'connected'
    reader, writer = BrokenReader(), BrokenWriter()
    run(client.shell(reader, writer))
    assert not client.connected
    assert reader.eof_fed and writer.connection_closed
    assert backend.status_list() == ['disconnected']
    # not a user disconnect, so reader_thread() retries
    assert not client.user_closed

class ClosingReader(BrokenReader):
    """a telnet reader that reaches EOF while the operator's close arrives"""
    def __init__(self, module):
        super().__init__()
        self.module = module
        self.eof = False

    async def read(self, n):
        self.module.stop_reader = True
        self.eof = True
        return ''

    def at_eof(self):
        return self.eof

def test_close_with_drop_in_shell(client):
    """a close that arrives as the connection drops isn't lost: shell() leaves stop_reader set, so
    reader_thread() stops instead of retrying (#167)"""
    Backend(client)
    run(client.shell(ClosingReader(client), BrokenWriter()))
    assert client.stop_reader

def test_close_with_drop(client, chipreader):
    """the same, end to end: the reader drops the connection just as Disconnect is clicked"""
    client.RECONNECT_WAIT = 1
    Backend(client)
    Ping(client)
    open_reader(client, chipreader.port)
    assert wait_until(lambda: status(client)['status'] == 'connected')
    chipreader.drop()
    control(client, {'opcode': 'close'})
    assert wait_until(lambda: not client.reader_thread_running, timeout=5)
    assert len(chipreader.writers) == 1
