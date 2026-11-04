'''the client post APIs: /_postresult, /_postbib (with the per-race debounce, #155), /_livechipreads
(GUNTIME start time), and the results view's start time and debounce controls'''
# standard
from datetime import datetime
from decimal import Decimal

# homegrown
from tm_csv_connector.model import db, Race, ChipRead, ChipBib
from helpers import make_race, post_result, post_bib, results, scans, log_events

def race(raceid):
    db.session.expire_all()
    return db.session.get(Race, raceid)

# /_postresult

def test_results_numbered_in_arrival_order(ctx, client):
    raceid = make_race()
    for pos, time in [(1, '00:20:01.50'), (2, '00:20:03.07'), (3, '00:19:59.00')]:
        assert post_result(client, raceid, pos, time) == {'status': 'success'}
    # places follow arrival, not time; times are stored in seconds
    assert [(r.place, r.tmpos, r.time, r.bibno, r.is_confirmed) for r in results(raceid)] == [
        (1, 1, 1201.5, None, False), (2, 2, 1203.07, None, False), (3, 3, 1199.0, None, False)]

def test_keypad_result(ctx, client):
    raceid = make_race()
    post_result(client, raceid, 1, '00:20:01.50', bibno=102)
    assert results(raceid)[0].bibno == '102'
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.new_bibno, entry.info) == ('result', '102', 'keypad bib')

def test_result_logged_with_device_time(ctx, client):
    raceid = make_race()
    post_result(client, raceid, 4, '00:20:01.50', device_time='2026-11-01T09:20:01.512')
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.place, entry.tmpos, entry.new_time, entry.info) == ('result', 1, 4, 1201.5, None)
    assert entry.device_time == datetime(2026, 11, 1, 9, 20, 1, 512000)
    assert entry.time.microsecond % 1000 == 0 and entry.time > entry.device_time

def test_bad_device_time_ignored(ctx, client):
    raceid = make_race()
    assert post_result(client, raceid, 1, '00:20:01.50', device_time='not a time')['status'] == 'success'
    assert log_events(raceid)[-1].device_time is None

def test_result_for_missing_race_refused(ctx, client):
    """a client still on race 0, e.g., after a restart, gets a refusal, not a 5xx (#147, #163)"""
    rsp = post_result(client, 0, 1, '00:20:01.50')
    assert rsp['status'] == 'fail' and 'IntegrityError' in rsp['error']

def test_first_result_truncates_output_file(ctx, client, outfile):
    raceid = make_race()
    outfile.write_bytes(b'left over\r\n')
    post_result(client, raceid, 1, '00:20:01.50')
    assert outfile.read_bytes() == b''
    outfile.write_bytes(b'kept\r\n')
    post_result(client, raceid, 2, '00:20:02.50')
    assert outfile.read_bytes() == b'kept\r\n'

# /_postbib

def test_scans_numbered_in_arrival_order(ctx, client):
    raceid = make_race()
    for bib in ('0042', '7', '0000', '0042'):
        assert post_bib(client, raceid, bib) == {'status': 'success'}
    # leading zeros are removed, except from the blank scan
    assert scans(raceid) == ['42', '7', '0000', '42']
    entries = log_events(raceid)
    assert [(e.event, e.scanbibno, e.info) for e in entries] == [
        ('scan', '42', 'scan 1'), ('scan', '7', 'scan 2'), ('scan', '0000', 'scan 3'), ('scan', '42', 'scan 4')]

def test_repeat_scan_kept_without_debounce(ctx, client):
    raceid = make_race(debounce_scans=False)
    post_bib(client, raceid, '42')
    post_bib(client, raceid, '42')
    assert scans(raceid) == ['42', '42']

def test_repeat_scan_ignored_with_debounce(ctx, client):
    raceid = make_race(debounce_scans=True)
    post_bib(client, raceid, '42')
    assert post_bib(client, raceid, '0042', device_time='2026-11-01T09:20:01.512') == {'status': 'success'}
    assert scans(raceid) == ['42']
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.scanbibno, entry.info) == ('scan ignored', '42', 'same bib as the previous scan')
    assert entry.device_time == datetime(2026, 11, 1, 9, 20, 1, 512000)

def test_debounce_only_catches_back_to_back(ctx, client):
    """A, B, A is kept; there's no time window"""
    raceid = make_race(debounce_scans=True)
    for bib in ('42', '43', '42'):
        post_bib(client, raceid, bib)
    assert scans(raceid) == ['42', '43', '42']

def test_blank_scans_never_debounced(ctx, client):
    raceid = make_race(debounce_scans=True)
    post_bib(client, raceid, '0000')
    post_bib(client, raceid, '0000')
    assert scans(raceid) == ['0000', '0000']

def test_debounce_checkbox(ctx, client):
    raceid = make_race(debounce_scans=False)
    rsp = client.post('/_setracedebouncescans', data={'raceid': raceid, 'debounce_scans': 'true'}).get_json()
    assert rsp == {'status': 'success', 'debounce_scans': True}
    assert race(raceid).debounce_scans
    # no change, so not logged again
    client.post('/_setracedebouncescans', data={'raceid': raceid, 'debounce_scans': 'true'})
    client.post('/_setracedebouncescans', data={'raceid': raceid, 'debounce_scans': 'false'})
    assert [(e.event, e.info) for e in log_events(raceid)] == [('Ignore repeat scans', 'on'), ('Ignore repeat scans', 'off')]
    assert client.get(f'/_getracestarttime?raceid={raceid}').get_json()['debounce_scans'] is False

# start time

def test_set_start_time(ctx, client):
    raceid = make_race(start_time=None)
    rsp = client.post('/_setracestarttime', data={'raceid': raceid, 'start_time': '9:00:00'}).get_json()
    assert rsp == {'status': 'success', 'start_time': '9:00:00.00'}
    assert race(raceid).start_time == 32400.0
    assert client.get(f'/_getracestarttime?raceid={raceid}').get_json() == {'start_time': '9:00:00.00', 'debounce_scans': False}
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.info) == ('Set start time', '(none) -> 9:00:00.00')

def test_bad_start_time_refused(ctx, client):
    raceid = make_race(start_time=100.0)
    rsp = client.post('/_setracestarttime', data={'raceid': raceid, 'start_time': '9:60'}).get_json()
    assert rsp['status'] == 'fail'
    assert race(raceid).start_time == 100.0

# /_livechipreads

def guntime(hhmmss, hundredths_hex='00', reader='A'):
    """marker line, see tridentmarker2obj()"""
    return f'ab{reader}00000260706' + '00' + hhmmss + hundredths_hex

def chipread(tag, hhmmss, rtype='RR', reader='A', rssi='5A'):
    """chip read line, see tridentread2obj()"""
    return f'aa{reader}1{tag}0001260706{hhmmss}1E00{rtype}{rssi}'

def post_chipreads(client, raceid, *lines):
    resp = client.post('/_livechipreads', json={'raceid': raceid, 'data': '\r\n'.join(lines) + '\r\n'})
    assert resp.status_code == 200
    return resp.get_json()

def test_first_guntime_sets_start_time(ctx, client):
    raceid = make_race(start_time=36000.0)
    assert post_chipreads(client, raceid, guntime('103000', '0A')) == {'status': 'success'}
    assert race(raceid).start_time == 37800.1
    entry = log_events(raceid)[-1]
    assert (entry.event, entry.info) == ('start time', '10:00:00.00 -> 10:30:00.10 from live GUNTIME')
    # later markers, e.g., from a second reader, are ignored
    post_chipreads(client, raceid, guntime('103100', reader='B'))
    assert race(raceid).start_time == 37800.1
    db.session.expire_all()
    assert ChipRead.query.filter_by(race_id=raceid, types='GUNTIME').count() == 2

def test_repeated_guntime_ignored(ctx, client):
    raceid = make_race()
    post_chipreads(client, raceid, guntime('103000'))
    post_chipreads(client, raceid, guntime('103000'))
    db.session.expire_all()
    assert ChipRead.query.filter_by(race_id=raceid).count() == 1

def test_chip_reads(ctx, client):
    raceid = make_race()
    db.session.add(ChipBib(race_id=raceid, tag_id='058000123456', bib=101))
    db.session.commit()
    post_chipreads(client, raceid, chipread('058000123456', '104530'), chipread('058000999999', '104531'))
    db.session.expire_all()
    reads = ChipRead.query.filter_by(race_id=raceid).order_by(ChipRead.time).all()
    assert [(r.tag_id, r.bib, r.time, r.types, r.rssi, r.source) for r in reads] == [
        ('058000123456', 101, Decimal('38730.30'), 'RR', 0x5a, 'live'),
        ('058000999999', None, Decimal('38731.30'), 'RR', 0x5a, 'live')]
    # the same read from the filtered stream is merged
    post_chipreads(client, raceid, chipread('058000123456', '104530', rtype='FS'))
    db.session.expire_all()
    assert ChipRead.query.filter_by(race_id=raceid, tag_id='058000123456').one().types == 'FS,RR'
    # chip reads don't change the start time
    assert race(raceid).start_time == 0.0
