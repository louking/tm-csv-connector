'''the output CSV that RaceDay Scoring reads: what Confirm appends, and when the file is rewritten'''
# homegrown
from tm_csv_connector.model import Result
from tm_csv_connector.fileformat import fulltime, db2file
from helpers import make_race, add_results, select_race, results, editor_edit, log_events, confirm, ok

START = 8 * 3600.0

def setup_race(client, start_time=START):
    raceid = make_race(start_time=start_time)
    ids = add_results(raceid, [('101', 'A'), ('102', 'B'), (None, None), ('104', None)])
    select_race(client, raceid)
    return raceid, ids

def lines(path):
    return path.read_text().splitlines()

def test_fulltime():
    assert fulltime(0) == '00:00:00.00'
    assert fulltime(61.5) == '00:01:01.50'
    assert fulltime(8 * 3600 + 59.99) == '08:00:59.99'
    assert fulltime(10 * 3600 + 12 * 60 + 3.07) == '10:12:03.07'

def test_db2file_adds_start_time(ctx):
    raceid = make_race(start_time=START)
    add_results(raceid, [('101', None)])
    # values as the csv writer writes them
    assert {k: str(v) for k, v in db2file(results(raceid)[0]).items()} == {'pos': '1', 'bibno': '101', 'time': '08:01:00.00'}

def test_confirm_appends(ctx, client, outfile):
    raceid, ids = setup_race(client)
    assert ok(confirm(client, ids[1]))
    assert lines(outfile) == ['1,101,08:01:00.00', '2,102,08:02:00.00']
    assert [r.is_confirmed for r in results(raceid)] == [True, True, False, False]
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.info) == ('Confirm', 2, '2 rows confirmed, up to place 2')
    # a later Confirm appends only the newly confirmed rows; no bib is written as empty
    confirm(client, ids[3])
    assert lines(outfile) == ['1,101,08:01:00.00', '2,102,08:02:00.00', '3,,08:03:00.00', '4,104,08:04:00.00']

def test_confirm_doesnt_change_row(ctx, client, outfile):
    raceid, ids = setup_race(client)
    before = [(r.place, r.bibno, r.time) for r in results(raceid)]
    confirm(client, ids[1])
    assert [(r.place, r.bibno, r.time) for r in results(raceid)] == before
    assert [e.event for e in log_events(raceid)] == ['Confirm']

def test_edit_confirmed_row_rewrites_file(ctx, client, outfile):
    raceid, ids = setup_race(client)
    confirm(client, ids[1])
    outfile.write_text('stale\r\n')
    editor_edit(client, ids[0], '201', 1, 60.0)
    assert lines(outfile) == ['1,201,08:01:00.00', '2,102,08:02:00.00']

def test_edit_unconfirmed_row_leaves_file(ctx, client, outfile):
    raceid, ids = setup_race(client)
    confirm(client, ids[1])
    before = outfile.read_text()
    editor_edit(client, ids[3], '204', 4, 240.0)
    assert outfile.read_text() == before

def test_race_change_rewrites_file(ctx, client, outfile):
    """/_setparams with race_changed writes the newly selected race's confirmed rows"""
    raceid, ids = setup_race(client)
    confirm(client, ids[0])
    other, other_ids = setup_race(client, start_time=9 * 3600.0)
    confirm(client, other_ids[1])
    assert len(lines(outfile)) == 3
    rsp = client.post('/_setparams', data={'raceid': raceid, 'race_changed': 'true'}).get_json()
    assert rsp == {'status': 'success', 'start_time': '8:00:00.00', 'debounce_scans': False}
    assert lines(outfile) == ['1,101,08:01:00.00']
    client.post('/_setparams', data={'raceid': other, 'race_changed': 'true'})
    assert lines(outfile) == ['1,101,09:01:00.00', '2,102,09:02:00.00']

def test_setparams_selects_race(ctx, client):
    raceid, ids = setup_race(client)
    other = make_race(name='other')
    client.post('/_setparams', data={'raceid': other})
    assert client.get('/results/rest').get_json() == []
    client.post('/_setparams', data={'raceid': raceid})
    assert len(client.get('/results/rest').get_json()) == 4

def test_no_output_setting_writes_nothing(ctx, client, output_dir):
    raceid, ids = setup_race(client)
    assert ok(confirm(client, ids[1]))
    assert list(output_dir.iterdir()) == []
