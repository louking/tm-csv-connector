'''helpers for the app tests: build races, and drive the endpoints as the browser and clients do

ORM objects are detached after each request (see conftest.ctx), so these take and return ids.
'''
# standard
from datetime import date

# homegrown
from tm_csv_connector.model import db, Race, Result, ScannedBib, ResultsLog
from tm_csv_connector.times import time2asc

def make_race(name='test race', start_time=0.0, **kwargs):
    race = Race(name=name, date=date.today(), start_time=start_time, **kwargs)
    db.session.add(race)
    db.session.commit()
    return race.id

def add_results(raceid, rows, scanned=True):
    """add results directly, with a scan for each that has one, as if the queue had assigned them

    Args:
        raceid (int): race
        rows ([(bibno, scan), ...]): result bib (or None) and scanned bib (or None, for no scan) in
            place order; times are 60s apart
        scanned (bool): False to leave had_scannedbib unset, for the queue to assign the scans

    Returns:
        [int]: result ids, in place order
    """
    ids = []
    order = 0
    for place, (bibno, scan) in enumerate(rows, start=1):
        sb = None
        if scan is not None:
            order += 1
            sb = ScannedBib(race_id=raceid, order=order, bibno=scan)
            db.session.add(sb)
        r = Result(race_id=raceid, tmpos=place, place=place, bibno=bibno, time=60.0 * place,
                   is_confirmed=False, scannedbib=sb if scanned else None,
                   had_scannedbib=bool(scanned and sb))
        db.session.add(r)
        db.session.flush()
        ids.append(r.id)
    db.session.commit()
    return ids

def select_race(client, raceid):
    """as the results page's race dropdown does, without the CSV rewrite"""
    with client.session_transaction() as s:
        s['_results_raceid'] = str(raceid)

def post_result(client, raceid, pos, time, bibno=None, device_time=None):
    """as tm-reader-client does; a bibno makes it a keypad (select) result"""
    msg = {'opcode': 'select' if bibno is not None else 'primary', 'raceid': str(raceid), 'pos': pos, 'time': time}
    if bibno is not None:
        msg['bibno'] = bibno
    if device_time:
        msg['device_time'] = device_time
    resp = client.post('/_postresult', json=msg)
    assert resp.status_code == 200
    return resp.get_json()

def post_bib(client, raceid, bibno, device_time=None):
    """as barcode-scanner-client does"""
    msg = {'opcode': 'scannedbib', 'raceid': str(raceid), 'bibno': bibno}
    if device_time:
        msg['device_time'] = device_time
    resp = client.post('/_postbib', json=msg)
    assert resp.status_code == 200
    return resp.get_json()

def poll(client):
    """get the results table as the results page's poll does

    Returns:
        {place: row dict}
    """
    resp = client.get('/results/rest')
    assert resp.status_code == 200, resp.status_code
    return {r['placepos']: r for r in resp.get_json()}

def scan_action(client, action, resultid, scanid):
    """press Use, Ins, or Del; scanid is the scan the button was drawn with, or None"""
    resp = client.post('/_scanaction', data={'action': action, 'resultid': resultid,
                                             'scanid': 'null' if scanid is None else scanid})
    assert resp.status_code == 200
    return resp.get_json()

def editor_data(rowkey, bibno, tmpos, secs, **extra):
    data = {f'data[{rowkey}][bibno]': '' if bibno is None else bibno, f'data[{rowkey}][tmpos]': tmpos,
            f'data[{rowkey}][time]': time2asc(secs), f'data[{rowkey}][scanned_bibno]': ''}
    for key, value in extra.items():
        data[f'data[{rowkey}][{key}]'] = value
    return data

def editor_edit(client, rid, bibno, tmpos, secs, **extra):
    """inline edit, or Confirm with confirm='true'; returns the response json"""
    resp = client.put(f'/results/rest/{rid}', data={'action': 'edit', **editor_data(rid, bibno, tmpos, secs, **extra)})
    assert resp.status_code == 200
    return resp.get_json()

def editor_create(client, bibno, tmpos, secs):
    resp = client.post('/results/rest', data={'action': 'create', **editor_data(0, bibno, tmpos, secs)})
    assert resp.status_code == 200
    return resp.get_json()

def editor_delete(client, rid):
    resp = client.delete(f'/results/rest/{rid}?action=remove')
    assert resp.status_code == 200
    return resp.get_json()

def ok(json):
    """editor response had no errors"""
    return not json.get('fieldErrors') and not json.get('error')

def confirm(client, rid):
    """press Confirm with the row selected"""
    r = db.session.get(Result, rid)
    db.session.refresh(r)
    return editor_edit(client, rid, r.bibno, r.tmpos, r.time, confirm='true')

def results(raceid):
    """the race's results, in place order, freshly read"""
    db.session.expire_all()
    return Result.query.filter_by(race_id=raceid).order_by(Result.place).all()

def queue(raceid):
    """(result bib, scanned bib) for each result, in place order; scanned bib is None if unassigned"""
    return [(r.bibno, r.scannedbib.bibno if r.scannedbib else None) for r in results(raceid)]

def scans(raceid):
    """scanned bibs in order"""
    db.session.expire_all()
    return [sb.bibno for sb in ScannedBib.query.filter_by(race_id=raceid).order_by(ScannedBib.order)]

def log_events(raceid):
    """the race's results log entries, in the order they were added"""
    db.session.expire_all()
    return ResultsLog.query.filter_by(race_id=raceid).order_by(ResultsLog.id).all()
