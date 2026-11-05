'''Undo of a Use scan action (#161)'''
# homegrown
from tm_csv_connector.model import db, Result
from helpers import (make_race, add_results, select_race, poll, scan_action, editor_edit, confirm,
                     queue, results, log_events, ok)

def scanid(resultid):
    db.session.expire_all()
    return db.session.get(Result, resultid).scannedbib_id

def before_use(resultid):
    db.session.expire_all()
    return db.session.get(Result, resultid).bibno_before_use

def setup_race(client, bibs=('101', '102', '103', '104')):
    """results with the given bibs, and scans A, B, C assigned to the first three"""
    raceid = make_race()
    ids = add_results(raceid, list(zip(bibs, ['A', 'B', 'C', None])))
    select_race(client, raceid)
    return raceid, ids

def use(client, rid):
    assert scan_action(client, 'use', rid, scanid(rid)) == {'status': 'success'}

def test_use_saves_bib_and_shows_undo(ctx, client):
    raceid, ids = setup_race(client)
    rows = poll(client)
    assert '>Use<' in rows[2]['scanned_bibno'] and '>Undo<' not in rows[2]['scanned_bibno']
    use(client, ids[1])
    assert before_use(ids[1]) == '102'
    rows = poll(client)
    assert '>Undo<' in rows[2]['scanned_bibno'] and '>Use<' not in rows[2]['scanned_bibno']
    assert 'action: &quot;undo&quot;' in rows[2]['scanned_bibno']
    # other rows keep Use
    assert '>Use<' in rows[1]['scanned_bibno']

def test_undo_restores_bib(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    assert scan_action(client, 'undo', ids[1], scanid(ids[1])) == {'status': 'success'}
    assert queue(raceid)[1] == ('102', 'B')
    assert before_use(ids[1]) is None
    rows = poll(client)
    assert '>Use<' in rows[2]['scanned_bibno'] and '>Undo<' not in rows[2]['scanned_bibno']
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.tmpos, entry.scanbibno, entry.old_bibno, entry.new_bibno) == \
        ('Undo', 2, 2, 'B', 'B', '102')

def test_undo_restores_blank_bib(ctx, client):
    raceid, ids = setup_race(client, bibs=(None, None, None, None))
    use(client, ids[0])
    assert before_use(ids[0]) == ''
    assert scan_action(client, 'undo', ids[0], scanid(ids[0])) == {'status': 'success'}
    assert queue(raceid)[0] == (None, 'A')
    assert before_use(ids[0]) is None
    assert log_events(raceid)[-1].new_bibno is None

def test_repeated_undo_is_stale(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    sid = scanid(ids[1])
    assert scan_action(client, 'undo', ids[1], sid)['status'] == 'success'
    assert scan_action(client, 'undo', ids[1], sid)['status'] == 'stale'
    assert queue(raceid)[1] == ('102', 'B')
    assert log_events(raceid)[-1].event == 'Undo stale'

def test_repeated_use_is_stale(ctx, client):
    # a second Use would save the scanned bib as the bib to restore
    raceid, ids = setup_race(client)
    use(client, ids[1])
    assert scan_action(client, 'use', ids[1], scanid(ids[1]))['status'] == 'stale'
    assert before_use(ids[1]) == '102'
    assert log_events(raceid)[-1].event == 'Use stale'

def test_undo_without_use_is_stale(ctx, client):
    raceid, ids = setup_race(client)
    assert scan_action(client, 'undo', ids[1], scanid(ids[1]))['status'] == 'stale'
    assert queue(raceid)[1] == ('102', 'B')

def test_inline_bib_edit_clears_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    r = results(raceid)[1]
    assert ok(editor_edit(client, ids[1], '202', r.tmpos, r.time))
    assert before_use(ids[1]) is None
    assert '>Undo<' not in poll(client)[2]['scanned_bibno']
    assert scan_action(client, 'undo', ids[1], scanid(ids[1]))['status'] == 'stale'
    assert queue(raceid)[1] == ('202', 'B')

def test_inline_time_edit_keeps_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    r = results(raceid)[1]
    assert ok(editor_edit(client, ids[1], r.bibno, r.tmpos, r.time + 0.5))
    assert before_use(ids[1]) == '102'

def test_insert_clears_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    use(client, ids[2])
    # Ins on the earlier row moves a different scan onto both
    assert scan_action(client, 'insert', ids[1], scanid(ids[1])) == {'status': 'success'}
    assert [before_use(i) for i in ids] == [None, None, None, None]

def test_insert_on_later_row_keeps_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[0])
    assert scan_action(client, 'insert', ids[1], scanid(ids[1])) == {'status': 'success'}
    assert before_use(ids[0]) == '101'

def test_delete_clears_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    use(client, ids[2])
    assert scan_action(client, 'delete', ids[1], scanid(ids[1])) == {'status': 'success'}
    assert before_use(ids[1]) is None
    assert before_use(ids[2]) is None

def test_confirm_clears_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[0])
    use(client, ids[2])
    assert ok(confirm(client, ids[1]))
    # confirmed rows lose Undo; later rows keep it
    assert [before_use(i) for i in ids] == [None, None, '103', None]
    rows = poll(client)
    assert '>Undo<' not in rows[1]['scanned_bibno']
    assert '>Undo<' in rows[3]['scanned_bibno']
    assert scan_action(client, 'undo', ids[0], scanid(ids[0]))['status'] == 'stale'

def test_clear_all_and_undo_clear_keep_undo(ctx, client):
    raceid, ids = setup_race(client)
    use(client, ids[1])
    assert client.post('/_clearresults', json={'raceid': raceid}).get_json()['status'] == 'success'
    assert client.post('/_undoclearresults', json={'raceid': raceid}).get_json()['status'] == 'success'
    assert [r.bibno_before_use for r in results(raceid)] == [None, '102', None, None]
