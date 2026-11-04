'''the results log (#157): what a race's log holds, and the Results Log view'''
# standard
from datetime import datetime

# homegrown
from tm_csv_connector.model import db, Result, ResultsLog
from helpers import (make_race, select_race, post_result, post_bib, poll, scan_action, editor_edit,
                     editor_create, confirm, log_events)

def test_race_log(ctx, client, outfile):
    """a short race, with each kind of event, logged in order, by place, TM position, and bib"""
    raceid = make_race()
    select_race(client, raceid)
    post_result(client, raceid, 1, '00:20:00.00')
    post_bib(client, raceid, '11')
    post_result(client, raceid, 2, '00:20:05.00', bibno=12)
    post_bib(client, raceid, '13')
    poll(client)
    db.session.expire_all()
    ids = [r.id for r in Result.query.filter_by(race_id=raceid).order_by(Result.place)]
    scanids = [db.session.get(Result, i).scannedbib_id for i in ids]
    scan_action(client, 'use', ids[0], scanids[0])
    scan_action(client, 'insert', ids[1], scanids[1])
    editor_edit(client, ids[1], '13', 2, 1205.0)
    editor_create(client, '14', 0, 1210.0)
    confirm(client, ids[1])

    got = [(e.event, e.place, e.tmpos, e.scanbibno, e.old_bibno, e.new_bibno, e.old_time, e.new_time, e.info)
           for e in log_events(raceid)]
    assert got == [
        ('result', 1, 1, None, None, None, None, 1200.0, None),
        ('scan', None, None, '11', None, None, None, None, 'scan 1'),
        ('result', 2, 2, None, None, '12', None, 1205.0, 'keypad bib'),
        ('scan', None, None, '13', None, None, None, None, 'scan 2'),
        ('Use', 1, 1, '11', None, '11', None, None, None),
        ('Ins', 2, 2, '13', None, None, None, None, None),
        ('Edit', 2, 2, None, '12', '13', 1205.0, 1205.0, None),
        ('New', 3, 0, None, None, '14', None, 1210.0, None),
        ('Confirm', 2, 2, None, None, None, None, None, '2 rows confirmed, up to place 2'),
    ]
    # a mistaken Use can be undone by hand from the log's old_bibno (#161)
    assert all(e.race_id == raceid and e.simulationrun_id is None for e in log_events(raceid))

def get_log(client, query=''):
    resp = client.get(f'/resultslog/rest{query}')
    assert resp.status_code == 200
    return resp.get_json()

def test_view_defaults_to_session_race(ctx, client):
    raceid = make_race()
    other = make_race(name='other')
    post_result(client, raceid, 1, '00:20:00.00')
    post_result(client, other, 1, '00:20:00.00')
    post_result(client, other, 2, '00:20:01.00')
    select_race(client, raceid)
    assert [r['event'] for r in get_log(client)] == ['result']
    assert len(get_log(client, f'?source={other}')) == 2

def test_view_formats_times(ctx, client):
    raceid = make_race()
    select_race(client, raceid)
    post_result(client, raceid, 1, '00:20:00.10', device_time='2026-11-01T09:20:01.512')
    row = get_log(client)[0]
    assert row['device_time'] == '2026-11-01 09:20:01.512'
    assert row['new_time'] == '0:20:00.10' and row['old_time'] == ''

def test_view_without_valid_race_shows_nothing(ctx, client):
    """race_id=None would match every simulation run's log (#152)"""
    raceid = make_race()
    post_result(client, raceid, 1, '00:20:00.00')
    # an entry with no race, as a simulation run's has
    db.session.add(ResultsLog(race_id=None, time=datetime.now(), event='result'))
    db.session.commit()
    assert get_log(client) == []
    assert get_log(client, '?source=999999') == []
    assert get_log(client, '?source=junk') == []
