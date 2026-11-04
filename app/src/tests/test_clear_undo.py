'''Clear All snapshots and Undo Clear'''
# standard
from json import loads

# homegrown
from tm_csv_connector.model import db, Race, ResultsSnapshot
from helpers import make_race, add_results, select_race, post_bib, poll, queue, scans, results, log_events, confirm

def clear(client, raceid):
    resp = client.post('/_clearresults', json={'raceid': raceid})
    assert resp.status_code == 200
    return resp.get_json()

def undo(client, raceid):
    resp = client.post('/_undoclearresults', json={'raceid': raceid})
    assert resp.status_code == 200
    return resp.get_json()

def setup_race(client):
    raceid = make_race()
    add_results(raceid, [('101', 'A'), ('102', '0000'), ('103', None)])
    # a scan still in the queue
    post_bib(client, raceid, 'C')
    select_race(client, raceid)
    return raceid

def snapshot(raceid):
    db.session.expire_all()
    return ResultsSnapshot.query.filter_by(race_id=raceid).one_or_none()

def test_clear(ctx, client):
    raceid = setup_race(client)
    assert clear(client, raceid) == {'status': 'success', 'debounce_scans': True}
    assert results(raceid) == [] and scans(raceid) == []
    snap = snapshot(raceid)
    assert [(r['place'], r['bibno'], r['had_scannedbib']) for r in loads(snap.results_json)] == \
        [(1, '101', True), (2, '102', True), (3, '103', False)]
    assert [sb['bibno'] for sb in loads(snap.scannedbibs_json)] == ['A', '0000', 'C']
    # clearing is the pre-race step, so repeat scans are ignored from then on (#155)
    db.session.expire_all()
    assert db.session.get(Race, raceid).debounce_scans
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.info) == ('Clear All', '3 results and 3 scans cleared, ignore repeat scans turned on')

def test_clear_leaves_other_races(ctx, client):
    raceid = setup_race(client)
    other = make_race(name='other race')
    add_results(other, [('201', 'X')])
    clear(client, raceid)
    assert queue(other) == [('201', 'X')]

def test_undo_restores_rows_and_scan_links(ctx, client):
    raceid = setup_race(client)
    before = queue(raceid)
    before_scans = scans(raceid)
    clear(client, raceid)
    assert undo(client, raceid) == {'status': 'success'}
    assert queue(raceid) == before
    assert scans(raceid) == before_scans
    assert snapshot(raceid) is None
    # the queued scan is assigned when the next result arrives, as before the clear
    db.session.expire_all()
    rows = poll(client)
    assert len(rows) == 3
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.info) == ('Undo Clear', '3 results and 3 scans restored')
    # undo leaves ignore repeat scans as Clear All set it
    assert db.session.get(Race, raceid).debounce_scans

def test_second_clear_replaces_snapshot(ctx, client):
    raceid = setup_race(client)
    clear(client, raceid)
    clear(client, raceid)
    snap = snapshot(raceid)
    assert loads(snap.results_json) == [] and loads(snap.scannedbibs_json) == []
    assert undo(client, raceid) == {'status': 'success'}
    assert results(raceid) == []

def test_undo_without_snapshot(ctx, client):
    raceid = setup_race(client)
    assert undo(client, raceid) == {'status': 'fail', 'error': 'no snapshot to restore'}
    assert len(results(raceid)) == 3

def test_clear_and_undo_rewrite_output_file(ctx, client, outfile):
    raceid = setup_race(client)
    confirm(client, results(raceid)[1].id)
    confirmed = outfile.read_text()
    assert len(confirmed.splitlines()) == 2
    clear(client, raceid)
    assert outfile.read_text() == ''
    undo(client, raceid)
    assert outfile.read_text() == confirmed
