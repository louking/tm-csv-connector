'''duplicate and unknown bib flags on the results view, and the editor's fresh response flags (#158)

ported from tools/check-bib-flags.py
'''
# homegrown
from tm_csv_connector.model import db, ChipBib, Result
from helpers import make_race, add_results, select_race, poll, editor_edit, ok

def flags(row):
    return (sorted(c for c in row['DT_RowClass'].split() if c not in ('result-row', 'confirmed')),
            row.get('dup_places'))

def edited_row(json):
    assert ok(json), json
    return json['data'][0]

def setup_race(client):
    raceid = make_race()
    # results 101, 102, 101, 25, none; scans 101, 102, 101 (A, B, A), 0000 (blank), 103
    ids = add_results(raceid, [('101', '101'), ('102', '102'), ('101', '101'), ('25', '0000'), (None, '103')])
    select_race(client, raceid)
    return raceid, ids

def add_chipbibs(raceid, bibs):
    for bib in bibs:
        db.session.add(ChipBib(race_id=raceid, tag_id=f'T{bib}', bib=bib))
    db.session.commit()

def test_flags_without_chip2bib(ctx, client):
    setup_race(client)
    rows = poll(client)
    assert flags(rows[1]) == (['dup-bib', 'dup-scan'], {'bib': [3], 'scan': [3]})
    assert flags(rows[2]) == ([], {})
    assert flags(rows[3]) == (['dup-bib', 'dup-scan'], {'bib': [1], 'scan': [1]})
    # 25 isn't checked without a chip-to-bib map, and blank scans are never duplicates
    assert flags(rows[4]) == ([], {})
    assert flags(rows[5]) == ([], {})
    assert all('result-row' in r['DT_RowClass'].split() for r in rows.values())

def test_unknown_bib_with_chip2bib(ctx, client):
    raceid, ids = setup_race(client)
    add_chipbibs(raceid, (101, 102, 103))
    rows = poll(client)
    assert flags(rows[4]) == (['unknown-bib'], {})
    # leading zeros don't make a bib unknown
    editor_edit(client, ids[3], '0025', 4, 240.0)
    add_chipbibs(raceid, (25,))
    assert flags(poll(client)[4]) == ([], {})

def test_edit_response_has_fresh_flags(ctx, client):
    raceid, ids = setup_race(client)
    add_chipbibs(raceid, (101, 102, 103))

    row = edited_row(editor_edit(client, ids[2], '103', 3, 180.0))
    assert (row['placepos'],) + flags(row) == (3, ['dup-scan'], {'scan': [1]})
    assert flags(poll(client)[1]) == (['dup-scan'], {'scan': [3]})

    row = edited_row(editor_edit(client, ids[2], '99', 3, 180.0))
    assert (row['placepos'],) + flags(row) == (3, ['dup-scan', 'unknown-bib'], {'scan': [1]})

    # moving to 0:30 makes it place 1; the response has the recalculated place
    row = edited_row(editor_edit(client, ids[2], '102', 3, 30.0))
    assert (row['placepos'],) + flags(row) == (1, ['dup-bib', 'dup-scan'], {'bib': [3], 'scan': [2]})

def test_flag_clears(ctx, client):
    """DT_RowClass stays nonempty, so DataTables removes a flag that clears"""
    raceid, ids = setup_race(client)
    assert 'dup-bib' in poll(client)[3]['DT_RowClass']
    edited_row(editor_edit(client, ids[2], '104', 3, 180.0))
    assert poll(client)[1]['DT_RowClass'].split() == ['result-row', 'dup-scan']

def test_no_race_shows_no_rows(ctx, client):
    """with no race in the session, the view shows nothing, not every simulation result (#152)"""
    raceid = make_race()
    add_results(raceid, [('101', '101')])
    # a result with no race, as a simulation result has
    db.session.add(Result(race_id=None, tmpos=1, place=1, bibno='9', time=1.0, had_scannedbib=False))
    db.session.commit()
    assert poll(client) == {}
    # nor with a race that doesn't exist
    select_race(client, 999999)
    assert poll(client) == {}
