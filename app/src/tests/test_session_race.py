'''the results poll reports the session's race, so the page can resend its race if they differ, and the app
log shows when the session's race changes (#173)'''
# standard
from logging import INFO

# pypi
import pytest

# homegrown
from tm_csv_connector.views.public import home
from tm_csv_connector.views.public.home import RESULTS_RACE_HEADER, POLL_RACE_UNSET
from helpers import make_race, add_results, select_race

@pytest.fixture(autouse=True)
def reset_poll_race(monkeypatch):
    """each test starts as if the app had just started"""
    monkeypatch.setattr(home, 'last_poll_race_id', POLL_RACE_UNSET)

def get_poll(client):
    resp = client.get('/results/rest')
    assert resp.status_code == 200
    return resp

def clear_session_race(client):
    with client.session_transaction() as s:
        s.pop('_results_raceid', None)

def setparams(client, raceid, race_changed=False):
    """as setParams() in results.js does, or its resend after a mismatch without race_changed"""
    data = {'port': 'COM3', 'scannerport': 'COM4', 'raceid': str(raceid), 'logdir': ''}
    if race_changed:
        data['race_changed'] = 'true'
    resp = client.post('/_setparams', data=data)
    assert resp.status_code == 200
    assert resp.get_json()['status'] == 'success'

def poll_messages(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('results poll:')]

def setparams_messages(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('_setparams:')]

def test_header_gives_session_race(ctx, client):
    raceid = make_race()
    add_results(raceid, [('101', None)])
    select_race(client, raceid)
    resp = get_poll(client)
    assert resp.headers[RESULTS_RACE_HEADER] == str(raceid)
    # the body is still the bare row array that refresh_results_table() expects
    assert [r['bibno'] for r in resp.get_json()] == ['101']

def test_header_empty_without_session_race(ctx, client):
    raceid = make_race()
    add_results(raceid, [('101', None)])
    resp = get_poll(client)
    assert resp.headers[RESULTS_RACE_HEADER] == ''
    assert resp.get_json() == []

def test_header_empty_for_unknown_race(ctx, client):
    raceid = make_race()
    select_race(client, raceid + 1000)
    resp = get_poll(client)
    assert resp.headers[RESULTS_RACE_HEADER] == ''
    assert resp.get_json() == []

def test_page_has_no_header(ctx, client):
    raceid = make_race()
    select_race(client, raceid)
    resp = client.get('/results')
    assert resp.status_code == 200
    assert RESULTS_RACE_HEADER not in resp.headers

def test_resend_restores_race_without_rewriting_csv(ctx, client, outfile):
    raceid = make_race()
    add_results(raceid, [('101', None), ('102', None)])
    outfile.write_text('1,101,00:01:00.00\n')
    select_race(client, raceid)
    assert get_poll(client).headers[RESULTS_RACE_HEADER] == str(raceid)

    # the session loses the race: the table empties
    clear_session_race(client)
    resp = get_poll(client)
    assert (resp.headers[RESULTS_RACE_HEADER], resp.get_json()) == ('', [])

    # the page resends its race, without race_changed
    setparams(client, raceid)
    resp = get_poll(client)
    assert resp.headers[RESULTS_RACE_HEADER] == str(raceid)
    assert len(resp.get_json()) == 2
    assert outfile.read_text() == '1,101,00:01:00.00\n'

def test_poll_logs_race_changes_once(ctx, client, caplog):
    caplog.set_level(INFO)
    raceid = make_race()
    select_race(client, raceid)
    get_poll(client)
    get_poll(client)
    assert poll_messages(caplog) == [f'results poll: session race {POLL_RACE_UNSET} -> {raceid}']

    caplog.clear()
    clear_session_race(client)
    get_poll(client)
    get_poll(client)
    messages = poll_messages(caplog)
    assert len(messages) == 1
    assert messages[0].startswith(f'results poll: no valid race in session (was {raceid}); _results_raceid=None, cookies=[')
    assert "'session'" in messages[0]
    assert [r.levelname for r in caplog.records if r.getMessage() == messages[0]] == ['WARNING']

    caplog.clear()
    select_race(client, raceid)
    get_poll(client)
    assert poll_messages(caplog) == [f'results poll: session race none -> {raceid}']

def test_setparams_logs_race_change(ctx, client, outfile, caplog):
    caplog.set_level(INFO)
    race1 = make_race('race 1')
    race2 = make_race('race 2')
    setparams(client, race1, race_changed=True)
    assert setparams_messages(caplog) == [f"_setparams: session race None -> '{race1}' (race changed)"]

    # same race again: nothing logged
    caplog.clear()
    setparams(client, race1)
    assert setparams_messages(caplog) == []

    caplog.clear()
    setparams(client, race2, race_changed=True)
    assert setparams_messages(caplog) == [f"_setparams: session race '{race1}' -> '{race2}' (race changed)"]

    # a resend after the session lost the race
    caplog.clear()
    clear_session_race(client)
    setparams(client, race2)
    assert setparams_messages(caplog) == [f"_setparams: session race None -> '{race2}'"]
