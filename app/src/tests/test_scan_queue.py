'''scan queue assignment in ResultsView.get(), and the Use/Ins/Del scan actions in ScanActionApi.post()'''
# homegrown
from tm_csv_connector.model import db, Result, ScannedBib
from helpers import (make_race, add_results, select_race, post_result, post_bib, poll, scan_action,
                     queue, scans, results, log_events)

def scanid(resultid):
    db.session.expire_all()
    return db.session.get(Result, resultid).scannedbib_id

def setup_race(client):
    """results 101-104 with scans A, B, C assigned to the first three"""
    raceid = make_race()
    ids = add_results(raceid, [('101', 'A'), ('102', 'B'), ('103', 'C'), ('104', None)])
    select_race(client, raceid)
    return raceid, ids

# queue assignment

def test_poll_assigns_scans_in_order(ctx, client):
    raceid = make_race()
    select_race(client, raceid)
    for pos in (1, 2, 3):
        post_result(client, raceid, pos, f'00:0{pos}:00.00')
    post_bib(client, raceid, '11')
    post_bib(client, raceid, '12')
    # nothing is assigned until a poll
    assert queue(raceid) == [(None, None)] * 3
    poll(client)
    assert queue(raceid) == [(None, '11'), (None, '12'), (None, None)]
    post_bib(client, raceid, '13')
    rows = poll(client)
    assert queue(raceid) == [(None, '11'), (None, '12'), (None, '13')]
    # the poll that assigns a scan also shows it
    assert '13' in rows[3]['scanned_bibno']

def test_scans_before_results_wait_in_queue(ctx, client):
    raceid = make_race()
    select_race(client, raceid)
    for bib in ('11', '12'):
        post_bib(client, raceid, bib)
    post_result(client, raceid, 1, '00:01:00.00')
    poll(client)
    assert queue(raceid) == [(None, '11')]
    post_result(client, raceid, 2, '00:02:00.00')
    poll(client)
    assert queue(raceid) == [(None, '11'), (None, '12')]

def test_scan_buttons_rendered_only_with_scan(ctx, client):
    setup_race(client)
    rows = poll(client)
    assert 'scan-action-btn' in rows[1]['scanned_bibno']
    assert rows[4]['scanned_bibno'] is None

# Use

def test_use(ctx, client):
    raceid, ids = setup_race(client)
    assert scan_action(client, 'use', ids[1], scanid(ids[1])) == {'status': 'success'}
    assert queue(raceid)[1] == ('B', 'B')
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.tmpos, entry.scanbibno, entry.old_bibno, entry.new_bibno) == \
        ('Use', 2, 2, 'B', '102', 'B')

def test_use_without_scan_refused(ctx, client):
    raceid, ids = setup_race(client)
    rsp = scan_action(client, 'use', ids[3], None)
    assert rsp['error'] == ['Invalid scanid: null']
    assert queue(raceid)[3] == ('104', None)

# Ins

def test_insert(ctx, client):
    raceid, ids = setup_race(client)
    assert scan_action(client, 'insert', ids[1], scanid(ids[1])) == {'status': 'success'}
    # a blank scan is inserted at this result and later scans move one result later
    assert queue(raceid) == [('101', 'A'), ('102', '0000'), ('103', 'B'), ('104', 'C')]
    assert scans(raceid) == ['A', '0000', 'B', 'C']
    assert all(r.had_scannedbib for r in results(raceid))
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.scanbibno) == ('Ins', 2, 'B')

def test_insert_with_more_scans_than_results(ctx, client):
    """the last result's scan moves back into the queue, and the next result gets it"""
    raceid = make_race()
    ids = add_results(raceid, [('101', 'A'), ('102', 'B')])
    select_race(client, raceid)
    post_bib(client, raceid, 'C')
    scan_action(client, 'insert', ids[0], scanid(ids[0]))
    assert queue(raceid) == [('101', '0000'), ('102', 'A')]
    post_result(client, raceid, 3, '00:03:00.00')
    poll(client)
    assert queue(raceid)[2] == (None, 'B')
    post_result(client, raceid, 4, '00:04:00.00')
    poll(client)
    assert queue(raceid)[3] == (None, 'C')

# Del

def test_delete(ctx, client):
    raceid, ids = setup_race(client)
    assert scan_action(client, 'delete', ids[1], scanid(ids[1])) == {'status': 'success'}
    # the scan is deleted and later scans move one result earlier
    assert queue(raceid) == [('101', 'A'), ('102', 'C'), ('103', None), ('104', None)]
    assert scans(raceid) == ['A', 'C']
    db.session.expire_all()
    assert [sb.order for sb in ScannedBib.query.filter_by(race_id=raceid).order_by(ScannedBib.order)] == [1, 2]
    assert [r.had_scannedbib for r in results(raceid)] == [True, True, False, False]
    # the next scan goes to the first result without one
    post_bib(client, raceid, 'D')
    poll(client)
    assert queue(raceid)[2] == ('103', 'D')
    entry = [e for e in log_events(raceid) if e.event == 'Del'][-1]
    assert (entry.place, entry.scanbibno) == (2, 'B')

def test_insert_then_delete_restores_queue(ctx, client):
    raceid, ids = setup_race(client)
    before = queue(raceid)
    scan_action(client, 'insert', ids[1], scanid(ids[1]))
    scan_action(client, 'delete', ids[1], scanid(ids[1]))
    assert queue(raceid) == before[:3] + [('104', None)]
    assert scans(raceid) == ['A', 'B', 'C']

# stale and refused presses

def test_repeated_delete_is_stale(ctx, client):
    """a second press drawn with the old scan does nothing (#156)"""
    raceid, ids = setup_race(client)
    old = scanid(ids[1])
    scan_action(client, 'delete', ids[1], old)
    after = queue(raceid)
    rsp = scan_action(client, 'delete', ids[1], old)
    assert rsp['status'] == 'stale'
    assert queue(raceid) == after
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.info) == ('Del stale', 'row now has scan C')

def test_repeated_insert_is_stale(ctx, client):
    raceid, ids = setup_race(client)
    old = scanid(ids[1])
    scan_action(client, 'insert', ids[1], old)
    after = queue(raceid)
    assert scan_action(client, 'insert', ids[1], old)['status'] == 'stale'
    assert queue(raceid) == after

def test_result_without_race_refused(ctx, client):
    """a result with no race would make the queue filters match every simulation run's rows (#152)"""
    raceid, ids = setup_race(client)
    orphan = Result(race_id=None, tmpos=1, place=1, bibno='9', time=1.0, had_scannedbib=False)
    db.session.add(orphan)
    db.session.commit()
    before = queue(raceid)
    rsp = scan_action(client, 'delete', orphan.id, None)
    assert rsp['error'] == [f'result {orphan.id} has no race or simulation run for this mode']
    assert queue(raceid) == before

def test_invalid_result_refused(ctx, client):
    raceid, ids = setup_race(client)
    rsp = scan_action(client, 'insert', 999999, scanid(ids[0]))
    assert rsp['error'] == ['Invalid resultid: 999999']
