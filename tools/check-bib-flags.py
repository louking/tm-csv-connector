'''Checks the results view's duplicate and unknown bib flags (#158) against a temporary race.

Builds a race with the ORM, gets /results/rest as a poll does, edits rows through the editor
endpoints, and prints each row's flags and dup_places with what's expected. The race is deleted
afterwards. No row is confirmed, so the output CSV isn't touched. Normal mode only.

    docker cp tools/check-bib-flags.py tm-csv-connector-app-1:/tmp/
    MSYS_NO_PATHCONV=1 docker exec -w /app tm-csv-connector-app-1 sh -c 'PYTHONPATH=/app python /tmp/check-bib-flags.py'

Exits with status 1 if any check fails.
'''
import sys
from datetime import date
from app import app
from tm_csv_connector.model import db, Race, Result, ScannedBib, ChipBib
from tm_csv_connector.times import time2asc

HOST = {'Host': 'tm.localhost'}
failures = 0

def check(label, got, expected):
    global failures
    ok = got == expected
    if not ok:
        failures += 1
    print(f'{"ok  " if ok else "FAIL"} {label}: {got}' + ('' if ok else f', expected {expected}'))

def flags(row):
    return (sorted(c for c in row['DT_RowClass'].split() if c not in ('result-row', 'confirmed')),
            row.get('dup_places'))

def poll(client):
    resp = client.get('/results/rest', headers=HOST)
    assert resp.status_code == 200, resp.status_code
    return {r['placepos']: r for r in resp.get_json()}

def edit(client, rid, bib, tmpos, secs):
    resp = client.put(f'/results/rest/{rid}', headers=HOST, data={
        'action': 'edit', f'data[{rid}][bibno]': bib, f'data[{rid}][tmpos]': tmpos,
        f'data[{rid}][time]': time2asc(secs), f'data[{rid}][scanned_bibno]': ''})
    j = resp.get_json()
    assert not j.get('fieldErrors') and not j.get('error'), j
    return j['data'][0]

with app.app_context():
    race = Race(name='zz check bib flags', date=date.today(), start_time=0)
    db.session.add(race)
    db.session.flush()
    raceid = race.id
    try:
        # results 101, 102, 101, 25, none; scans 101, 102, 101 (A, B, A), 0000 (blank), 103
        bibs = ['101', '102', '101', '25', None]
        scans = ['101', '102', '101', '0000', '103']
        for i, (bib, scan) in enumerate(zip(bibs, scans), start=1):
            sb = ScannedBib(race_id=raceid, order=i, bibno=scan)
            db.session.add(sb)
            db.session.add(Result(race_id=raceid, tmpos=i, place=i, bibno=bib, time=60.0 * i,
                                  is_confirmed=False, scannedbib=sb, had_scannedbib=True))
        db.session.commit()
        ids = {r.place: r.id for r in Result.query.filter_by(race_id=raceid)}

        client = app.test_client()
        with client.session_transaction() as s:
            s['_results_raceid'] = str(raceid)

        print('no chip-to-bib map:')
        rows = poll(client)
        check('place 1', flags(rows[1]), (['dup-bib', 'dup-scan'], {'bib': [3], 'scan': [3]}))
        check('place 2', flags(rows[2]), ([], {}))
        check('place 3', flags(rows[3]), (['dup-bib', 'dup-scan'], {'bib': [1], 'scan': [1]}))
        check('place 4, 25 not checked without a map', flags(rows[4]), ([], {}))
        check('place 5, no bib', flags(rows[5]), ([], {}))

        for bib in (101, 102, 103):
            db.session.add(ChipBib(race_id=raceid, tag_id=f'T{bib}', bib=bib))
        db.session.commit()
        print('chip-to-bib map 101-103:')
        rows = poll(client)
        check('place 4, 25 not in race', flags(rows[4]), (['unknown-bib'], {}))

        print('edits; the response row has fresh flags:')
        row = edit(client, ids[3], '103', 3, 180.0)
        check('place 3 -> 103', (row['placepos'],) + flags(row), (3, ['dup-scan'], {'scan': [1]}))
        rows = poll(client)
        check('place 1 after the poll', flags(rows[1]), (['dup-scan'], {'scan': [3]}))
        row = edit(client, ids[3], '99', 3, 180.0)
        check('place 3 -> 99', (row['placepos'],) + flags(row), (3, ['dup-scan', 'unknown-bib'], {'scan': [1]}))
        row = edit(client, ids[3], '102', 3, 30.0)
        check('place 3 -> 102 at 0:30, moves to place 1', (row['placepos'],) + flags(row),
              (1, ['dup-bib', 'dup-scan'], {'bib': [3], 'scan': [2]}))
    finally:
        db.session.rollback()
        db.session.expire_all()
        race = db.session.get(Race, raceid)
        # results reference scans, so clear those before the cascade deletes both
        for r in race.results:
            r.scannedbib = None
        db.session.flush()
        db.session.delete(race)
        db.session.commit()

print('all checks pass' if not failures else f'{failures} check(s) failed')
sys.exit(1 if failures else 0)
