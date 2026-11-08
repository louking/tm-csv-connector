'''simulation mode (#167): the /admin endpoints the simulation page uses, the queries keyed on
simulationrun_id, and who can see the Results Log

Run with `pytest --sim`, see CLAUDE.md.
'''
# homegrown
from tm_csv_connector.model import db, Result, ScannedBib, ResultsLog, SimulationResult, SimulationRun
from tm_csv_connector.times import time2asc
from helpers import make_race, add_results, queue, scans
from simhelpers import (login, make_run, select_run, add_sim_results, sim_post_result, sim_post_bib, sim_poll,
                        sim_scan_action, sim_results, sim_queue, sim_scans, user_id)

def test_posts_and_queue(app, ctx, client, users):
    """results and scans posted to a run get its places and order, and a poll assigns the run's scans
    to its results, without touching other runs or races"""
    login(client, users['admin'])
    run_a = make_run(users['admin'])
    run_b = make_run(users['admin'], name='other simulation')
    raceid = make_race()
    add_results(raceid, [(None, None)])
    db.session.add(ScannedBib(race_id=raceid, order=1, bibno='901'))
    db.session.commit()

    for pos in (1, 2, 3):
        assert sim_post_result(client, run_a, pos, 60.0 * pos)['status'] == 'success'
    for bib in ('101', '0102'):
        assert sim_post_bib(client, run_a, bib)['status'] == 'success'
    sim_post_result(client, run_b, 1, 30.0)
    sim_post_bib(client, run_b, '201')

    select_run(client, run_a)
    rows = sim_poll(client)
    assert sorted(rows) == [1, 2, 3]
    assert [r.place for r in sim_results(run_a)] == [1, 2, 3]
    assert [r.time for r in sim_results(run_a)] == [60.0, 120.0, 180.0]
    # leading zeros are dropped, as in normal mode
    assert sim_queue(run_a) == [(None, '101'), (None, '102'), (None, None)]
    # run B's queue is assigned only when it's polled
    assert sim_queue(run_b) == [(None, None)]
    assert [r.place for r in sim_results(run_b)] == [1]
    # the race is untouched
    assert queue(raceid) == [(None, None)]

    select_run(client, run_b)
    assert sorted(sim_poll(client)) == [1]
    assert sim_queue(run_b) == [(None, '201')]

    # the results log is keyed on the run
    db.session.expire_all()
    log = ResultsLog.query.filter_by(simulationrun_id=run_a).order_by(ResultsLog.id).all()
    assert [(e.event, e.place, e.scanbibno) for e in log] == [
        ('result', 1, None), ('result', 2, None), ('result', 3, None), ('scan', None, '101'), ('scan', None, '102')]
    assert all(e.race_id is None for e in log)

def test_no_run_selected(app, ctx, client, users):
    """with no valid run in the session, the table shows no rows; simulationrun_id=None would match
    every race's results (#152)"""
    login(client, users['admin'])
    runid = make_run(users['admin'])
    add_sim_results(runid, [(None, '101')])
    raceid = make_race()
    add_results(raceid, [(None, '901'), (None, '902')])

    assert sim_poll(client) == {}
    select_run(client, 999999)
    assert sim_poll(client) == {}
    select_run(client, runid)
    assert sorted(sim_poll(client)) == [1]

def test_bib_scans_not_debounced(app, ctx, client, users):
    """simulation mode keeps repeat scans (the debounce is normal mode's, #155)"""
    runid = make_run(users['admin'])
    sim_post_bib(client, runid, '101')
    sim_post_bib(client, runid, '101')
    assert sim_scans(runid) == ['101', '101']

def test_scan_actions(app, ctx, client, users):
    """Del, Ins, Use, and Undo change only the run's queue, and a stale press is ignored"""
    login(client, users['admin'])
    run_a = make_run(users['admin'])
    run_b = make_run(users['admin'], name='other simulation')
    a1, a2, a3 = add_sim_results(run_a, [(None, '101'), (None, '102'), (None, '103')])
    add_sim_results(run_b, [(None, '201'), (None, '202'), (None, '203')])
    raceid = make_race()
    add_results(raceid, [(None, '901'), (None, '902')])
    select_run(client, run_a)

    def scanid(rid):
        db.session.expire_all()
        return db.session.get(Result, rid).scannedbib_id

    s1 = scanid(a1)
    assert sim_scan_action(client, 'delete', a1, s1)['status'] == 'success'
    assert sim_queue(run_a) == [(None, '102'), (None, '103'), (None, None)]
    # pressed again before the table refreshed
    assert sim_scan_action(client, 'delete', a1, s1)['status'] == 'stale'
    assert sim_scans(run_a) == ['102', '103']

    assert sim_scan_action(client, 'insert', a2, scanid(a2))['status'] == 'success'
    assert sim_queue(run_a) == [(None, '102'), (None, '0000'), (None, '103')]

    assert sim_scan_action(client, 'use', a1, scanid(a1))['status'] == 'success'
    assert [r.bibno for r in sim_results(run_a)] == ['102', None, None]
    assert sim_scan_action(client, 'undo', a1, scanid(a1))['status'] == 'success'
    assert [r.bibno for r in sim_results(run_a)] == [None, None, None]

    # other runs and races are untouched
    assert sim_queue(run_b) == [(None, '201'), (None, '202'), (None, '203')]
    assert queue(raceid) == [(None, '901'), (None, '902')]
    assert scans(raceid) == ['901', '902']

    db.session.expire_all()
    events = [e.event for e in ResultsLog.query.filter_by(simulationrun_id=run_a).order_by(ResultsLog.id)]
    assert events == ['Del', 'Del stale', 'Ins', 'Use', 'Undo']

def test_scan_action_on_race_result_refused(app, ctx, client, users):
    """a race's result has no simulation run, so a scan action on it is refused rather than shifting
    every race's scans (#152)"""
    login(client, users['admin'])
    raceid = make_race()
    r1, r2 = add_results(raceid, [(None, '901'), (None, '902')])
    db.session.expire_all()
    rsp = sim_scan_action(client, 'delete', r1, db.session.get(Result, r1).scannedbib_id)
    assert any('no race or simulation run' in e for e in rsp['error'])
    assert queue(raceid) == [(None, '901'), (None, '902')]

def test_confirm_records_simulation_results(app, ctx, client, users):
    """Confirm confirms the run's rows up to the selected one, and records them as the run's results"""
    login(client, users['admin'])
    runid = make_run(users['admin'])
    other = make_run(users['admin'], name='other simulation')
    r1, r2, r3 = add_sim_results(runid, [('101', '101'), ('102', '102'), (None, '103')])
    o1, = add_sim_results(other, [('201', '201')])
    select_run(client, runid)

    r = db.session.get(Result, r2)
    data = {'action': 'edit', f'data[{r2}][bibno]': r.bibno, f'data[{r2}][tmpos]': r.tmpos,
            f'data[{r2}][time]': time2asc(r.time), f'data[{r2}][scanned_bibno]': '', f'data[{r2}][confirm]': 'true'}
    resp = client.put(f'/admin/resultssim/rest/{r2}', data=data)
    assert resp.status_code == 200
    json = resp.get_json()
    assert not json.get('error') and not json.get('fieldErrors'), json

    assert [r.is_confirmed for r in sim_results(runid)] == [True, True, False]
    assert [r.is_confirmed for r in sim_results(other)] == [False]
    db.session.expire_all()
    simresults = SimulationResult.query.filter_by(simulationrun_id=runid).order_by(SimulationResult.order).all()
    assert [(s.order, s.bibno, s.time) for s in simresults] == [(1, '101', 60.0), (2, '102', 120.0)]
    assert SimulationResult.query.filter_by(simulationrun_id=other).count() == 0

def test_create_run_permission(app, ctx, client, users):
    """only tmsim and super admins can start a simulation run"""
    sim_runid = make_run(users['admin'])
    simid = db.session.get(SimulationRun, sim_runid).simulation_id
    form = {'simulation_id': simid, 'start_time': '08:00'}

    login(client, users['user'])
    rsp = client.post('/admin/_creategetsimulationrun', data=form).get_json()
    assert rsp['status'] == 'fail' and 'permission denied' in rsp['error']

    for who in ('admin', 'super'):
        login(client, users[who])
        rsp = client.post('/admin/_creategetsimulationrun', data=form).get_json()
        assert rsp['status'] == 'success', rsp
    db.session.expire_all()
    assert SimulationRun.query.filter_by(simulation_id=simid, user_id=user_id(users['user'])).count() == 0
    assert SimulationRun.query.filter_by(simulation_id=simid, user_id=user_id(users['super'])).count() == 1

def test_resultslog_permission(app, ctx, client, users):
    """only tmsim and super admins can see the Results Log, and it shows the run asked for"""
    run_a = make_run(users['user'])
    run_b = make_run(users['user'], name='other simulation')
    sim_post_result(client, run_a, 1, 60.0)
    sim_post_bib(client, run_b, '201')

    # not logged in, and a tmsim user
    assert client.get('/resultslog').status_code == 403
    login(client, users['user'])
    assert client.get('/resultslog').status_code == 403
    assert client.get(f'/resultslog/rest?source={run_a}').status_code == 403

    for who in ('admin', 'super'):
        login(client, users[who])
        assert client.get(f'/resultslog?source={run_a}').status_code == 200
        rows = client.get(f'/resultslog/rest?source={run_a}').get_json()
        assert [r['event'] for r in rows] == ['result']
        rows = client.get(f'/resultslog/rest?source={run_b}').get_json()
        assert [r['event'] for r in rows] == ['scan']
        # an id that isn't a simulation run shows nothing
        assert client.get('/resultslog/rest?source=999999').get_json() == []
