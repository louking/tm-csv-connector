'''requests racing for filelock (#167)

MySQL runs at REPEATABLE READ, and a request's snapshot is taken at its first query (the default-user
login), before it waits for filelock. So a request that waited can miss a change committed while it
waited, unless its reads under the lock are locking reads (#156). Each test here holds filelock,
starts a request in a thread and lets it reach the lock, commits a conflicting change, then releases
the lock and checks that the waiting request saw the change.
'''
# standard
from threading import Thread, Event, get_ident

# pypi
import pytest

# homegrown
from tm_csv_connector.model import db, Result, ScannedBib
from tm_csv_connector.fileformat import filelock
from tm_csv_connector.views import common
from tm_csv_connector.views.public import api
from helpers import make_race, add_results, select_race, post_result, post_bib, scan_action, queue, scans, results

class LockGate:
    """the test thread holds filelock; a request from another thread sets waiting when it reaches
    the lock, after its snapshot was taken

    Requests made from the test thread act as if they held the lock, so the test can commit the
    conflicting change with a real request while the other one waits.
    """
    def __init__(self, monkeypatch):
        self.owner = get_ident()
        self.waiting = Event()
        self.held = False
        for module in (common, api):
            monkeypatch.setattr(module, 'lock', self.lock)
            monkeypatch.setattr(module, 'unlock', self.unlock)

    def hold(self):
        filelock.acquire()
        self.held = True

    def release(self):
        if self.held:
            self.held = False
            filelock.release()

    def lock(self, thelock):
        if get_ident() == self.owner:
            return
        self.waiting.set()
        thelock.acquire()

    def unlock(self, thelock):
        if get_ident() == self.owner:
            return
        thelock.release()

class Request:
    """make a request in a thread with its own client; result holds the request function's return"""
    def __init__(self, app, func, prime=None):
        self.client = app.test_client()
        # a request first, so the user is logged in and the waiting request doesn't commit a login
        # before the lock, which would end its snapshot
        self.client.get('/_getracestarttime')
        if prime:
            prime(self.client)
        self.func = func
        self.result = None
        self.error = None
        self.thread = Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self.result = self.func(self.client)
        except Exception as e:
            self.error = e

    def start(self):
        self.thread.start()
        return self

    def join(self):
        self.thread.join(timeout=30)
        assert not self.thread.is_alive(), 'request did not finish'
        if self.error:
            raise self.error
        return self.result

@pytest.fixture
def gate(monkeypatch):
    gate = LockGate(monkeypatch)
    yield gate
    gate.release()

def race_after_wait(app, gate, waiting_request, conflicting_change, prime=None):
    """run waiting_request(client) in a thread until it waits for filelock, run conflicting_change()
    from this thread, then let the waiting request go; returns its result"""
    req = Request(app, waiting_request, prime)
    gate.hold()
    req.start()
    assert gate.waiting.wait(10), 'request never reached filelock'
    try:
        conflicting_change()
    finally:
        gate.release()
    return req.join()

def scanid(rid):
    db.session.expire_all()
    return db.session.get(Result, rid).scannedbib_id

def test_del_on_adjacent_rows(app, ctx, client, gate):
    """Del on two adjacent rows 0.7s apart: the first moved the second row's scan up, so the second
    press is stale. Before the fix it deleted the scan the first Del had moved, and failed with a
    result.scannedbib_id foreign-key error (#156)"""
    raceid = make_race()
    r1, r2, r3 = add_results(raceid, [(None, '101'), (None, '102'), (None, '103')])
    s1, s2 = scanid(r1), scanid(r2)

    rsp = race_after_wait(app, gate,
                          lambda c: scan_action(c, 'delete', r2, s2),
                          lambda: scan_action(client, 'delete', r1, s1))
    assert rsp['status'] == 'stale'
    assert queue(raceid) == [(None, '102'), (None, '103'), (None, None)]
    assert scans(raceid) == ['102', '103']

def test_repeated_ins(app, ctx, client, gate):
    """a second Ins press on the same row, drawn with the same scan, is stale"""
    raceid = make_race()
    r1, r2 = add_results(raceid, [(None, '101'), (None, '102')])
    s1 = scanid(r1)

    rsp = race_after_wait(app, gate,
                          lambda c: scan_action(c, 'insert', r1, s1),
                          lambda: scan_action(client, 'insert', r1, s1))
    assert rsp['status'] == 'stale'
    assert scans(raceid) == ['0000', '101', '102']

def test_poll_behind_undo_clear(app, ctx, client, gate):
    """a poll waiting behind Undo Clear, which inserts scans with new ids. Before the fix the poll
    read the last result's scan from its snapshot, got None, and returned a 500 (#156)"""
    raceid = make_race()
    add_results(raceid, [(None, '101'), (None, '102')])
    assert client.post('/_clearresults', json={'raceid': raceid}).get_json()['status'] == 'success'

    rsp = race_after_wait(app, gate,
                          lambda c: c.get('/results/rest'),
                          lambda: client.post('/_undoclearresults', json={'raceid': raceid}),
                          prime=lambda c: select_race(c, raceid))
    assert rsp.status_code == 200
    assert queue(raceid) == [(None, '101'), (None, '102')]

def test_results_posted_together(app, ctx, client, gate):
    """two Time Machine results: the second must see the first's place"""
    raceid = make_race()
    add_results(raceid, [(None, None)])

    rsp = race_after_wait(app, gate,
                          lambda c: post_result(c, raceid, 3, '00:03:00.00'),
                          lambda: post_result(client, raceid, 2, '00:02:00.00'))
    assert rsp['status'] == 'success'
    assert [(r.tmpos, r.place) for r in results(raceid)] == [(1, 1), (2, 2), (3, 3)]

def test_scans_posted_together(app, ctx, client, gate):
    """two scans: the second must see the first's order"""
    raceid = make_race()

    rsp = race_after_wait(app, gate,
                          lambda c: post_bib(c, raceid, '102'),
                          lambda: post_bib(client, raceid, '101'))
    assert rsp['status'] == 'success'
    db.session.expire_all()
    assert [(sb.order, sb.bibno) for sb in ScannedBib.query.filter_by(race_id=raceid).order_by(ScannedBib.order)] == \
        [(1, '101'), (2, '102')]

def test_clear_all_behind_result(app, ctx, client, gate):
    """Clear All waiting behind a result post: the result it deletes must be in its snapshot, so
    Undo Clear restores it"""
    raceid = make_race()
    add_results(raceid, [(None, '101')])

    rsp = race_after_wait(app, gate,
                          lambda c: c.post('/_clearresults', json={'raceid': raceid}).get_json(),
                          lambda: post_result(client, raceid, 2, '00:02:00.00'))
    assert rsp['status'] == 'success'
    assert results(raceid) == []
    assert client.post('/_undoclearresults', json={'raceid': raceid}).get_json()['status'] == 'success'
    assert [r.tmpos for r in results(raceid)] == [1, 2]
