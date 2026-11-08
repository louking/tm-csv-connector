'''pytest setup for the client tests (#166)

These run on Windows in the repo's .venv, not in the app container, and need no devices or backend:
device bytes go through a pyserial loop:// port, and posts go to a fake. trident-reader-client's tests
(test_trident.py, #167) use a fake chip reader on localhost instead. See CLAUDE.md.

Each test gets a freshly loaded copy of the client module, since the clients keep their state
(raceid, queued_msgs, stop_reader, ...) in module globals.
'''
# standard
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from json import dumps, loads
from asyncio import run, new_event_loop, set_event_loop
from itertools import count

# pypi
import pytest
from requests import ConnectionError

REPO = Path(__file__).resolve().parents[2]
_loaded = count()

def load_client(dirname):
    spec = spec_from_file_location(f'{dirname.replace("-", "_")}_{next(_loaded)}', REPO / dirname / 'app.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    # fast retries, so the tests don't wait out the real 1-5s
    module.POST_RETRY_WAITS = [0.05, 0.1, 0.2]
    module.RECONNECT_WAIT = 1
    return module

@pytest.fixture
def tm():
    return load_client('tm-reader-client')

@pytest.fixture
def scanner():
    return load_client('barcode-scanner-client')

@pytest.fixture
def trident():
    return load_client('trident-reader-client')

def wait_until(condition, timeout=5.0, interval=0.02):
    """wait for condition() to be true; returns its last value"""
    end = monotonic() + timeout
    while True:
        value = condition()
        if value or monotonic() > end:
            return value
        sleep(interval)

class Response:
    def __init__(self, status_code, json=None, text=None):
        self.status_code = status_code
        self.text = text if text is not None else dumps(json)

class FakeBackend:
    """stands in for requests.post in a client module

    outcomes are used in turn for each post, then every later post succeeds; an outcome is a
    Response, or an exception to raise. accepted holds the messages the backend accepted, in order
    """
    def __init__(self, module, outcomes=()):
        self.outcomes = list(outcomes)
        self.posts = []
        self.accepted = []
        module.post = self.post

    def post(self, url, json=None, timeout=None):
        self.posts.append(json)
        outcome = self.outcomes.pop(0) if self.outcomes else Response(200, {'status': 'success'})
        if isinstance(outcome, Exception):
            raise outcome
        if outcome.status_code == 200 and outcome.text == dumps({'status': 'success'}):
            self.accepted.append(json)
        return outcome

def connection_refused():
    return ConnectionError('connection refused')

class LoopReader:
    """run a client's reader() on a loop:// port in its own thread, capturing the serial port so
    the test can write device bytes to it, as tools did by hand before #166"""
    def __init__(self, module, wrap_name):
        self.module = module
        self.serial = None
        self.error = None
        original = getattr(module, wrap_name)

        async def wrapper(loop, protocol_factory, port_or_serial, *args, **kwargs):
            transport, protocol = await original(loop, protocol_factory, port_or_serial, *args, **kwargs)
            ser = transport.serial
            # pyserial-asyncio sets this to 0, and then every loop:// write fails with Write timeout
            ser.write_timeout = None
            self.serial = ser
            return transport, protocol

        setattr(module, wrap_name, wrapper)
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()
        assert wait_until(lambda: self.serial is not None or self.error), 'port not opened'
        assert self.error is None, self.error

    def _run(self):
        set_event_loop(new_event_loop())
        try:
            run(self.module.reader('loop://', None))
        except Exception as e:
            self.error = e

    def write(self, data):
        self.serial.write(data)

    def stop(self):
        self.module.stop_reader = True
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), 'reader did not stop'

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
