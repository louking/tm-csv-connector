'''inline edits, New, and Delete through the results view's editor endpoints, with place recalculation'''
# homegrown
from tm_csv_connector.model import db, Result
from helpers import (make_race, add_results, select_race, poll, editor_edit, editor_create, editor_delete, ok,
                     results, queue, log_events)

def places(raceid):
    return [(r.place, r.bibno) for r in results(raceid)]

def setup_race(client, rows=(('101', 'A'), ('102', 'B'), ('103', None))):
    raceid = make_race()
    ids = add_results(raceid, list(rows))
    select_race(client, raceid)
    return raceid, ids

def test_edit_bib(ctx, client):
    raceid, ids = setup_race(client)
    assert ok(editor_edit(client, ids[0], '201', 1, 60.0))
    assert places(raceid) == [(1, '201'), (2, '102'), (3, '103')]
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.tmpos, entry.old_bibno, entry.new_bibno, entry.info) == \
        ('Edit', 1, 1, '101', '201', None)

def test_edit_time_reorders_places(ctx, client):
    raceid, ids = setup_race(client)
    assert ok(editor_edit(client, ids[2], '103', 3, 30.0))
    assert places(raceid) == [(1, '103'), (2, '101'), (3, '102')]
    # scans stay with their results
    assert queue(raceid) == [('103', None), ('101', 'A'), ('102', 'B')]
    entry = log_events(raceid)[-1]
    # logged with the place it had when it was edited
    assert (entry.event, entry.place, entry.old_time, entry.new_time) == ('Edit', 3, 180.0, 30.0)

def test_edit_tmpos_logged(ctx, client):
    raceid, ids = setup_race(client)
    editor_edit(client, ids[1], '102', 7, 120.0)
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.tmpos, entry.info) == ('Edit', 2, 'TM Pos 2 -> 7')

def test_unchanged_edit_not_logged(ctx, client):
    raceid, ids = setup_race(client)
    editor_edit(client, ids[1], '102', 2, 120.0)
    assert log_events(raceid) == []

def test_bad_time_rejected(ctx, client):
    raceid, ids = setup_race(client)
    rsp = client.put(f'/results/rest/{ids[0]}', data={
        'action': 'edit', f'data[{ids[0]}][bibno]': '999', f'data[{ids[0]}][tmpos]': 1,
        f'data[{ids[0]}][time]': '1:75', f'data[{ids[0]}][scanned_bibno]': ''}).get_json()
    # a rejected edit still returns 200, with fieldErrors
    assert rsp['fieldErrors'] == [{'name': 'time', 'status': 'must be formatted as [[hh:]mm:]ss[.dd]'}]
    assert places(raceid)[0] == (1, '101')

def test_new(ctx, client):
    raceid, ids = setup_race(client)
    rsp = editor_create(client, '150', 0, 150.0)
    assert ok(rsp)
    assert places(raceid) == [(1, '101'), (2, '102'), (3, '150'), (4, '103')]
    new = [r for r in results(raceid) if r.bibno == '150'][0]
    assert new.race_id == raceid
    # the next result (103) has no scan, so neither does the new one
    assert not new.had_scannedbib
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.new_bibno, entry.new_time) == ('New', 3, '150', 150.0)

def test_new_before_scanned_result_takes_scan_slot(ctx, client):
    """a New result before one with a scan is marked as having had one, so the queue doesn't
    assign it a later scan"""
    raceid, ids = setup_race(client)
    editor_create(client, '50', 0, 30.0)
    new = results(raceid)[0]
    assert (new.bibno, new.had_scannedbib, new.scannedbib_id) == ('50', True, None)

def test_delete_without_scan(ctx, client):
    raceid, ids = setup_race(client)
    assert ok(editor_delete(client, ids[2]))
    assert places(raceid) == [(1, '101'), (2, '102')]
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.old_bibno, entry.old_time) == ('Delete', 3, '103', 180.0)

def test_delete_with_blank_scan(ctx, client):
    raceid, ids = setup_race(client, rows=(('101', '0000'), ('102', 'B')))
    assert ok(editor_delete(client, ids[0]))
    assert places(raceid) == [(1, '102')]

def test_delete_with_scan_refused(ctx, client):
    raceid, ids = setup_race(client)
    rsp = editor_delete(client, ids[0])
    assert 'cannot delete result which has scanned bib assigned' in rsp['error']
    assert len(results(raceid)) == 3
    assert log_events(raceid) == []

def test_poll_matches_editor_rows(ctx, client):
    """the poll and the editor response render a row the same way"""
    raceid, ids = setup_race(client)
    row = editor_edit(client, ids[0], '201', 1, 60.0)['data'][0]
    assert poll(client)[1] == row
