'''helpers for the simulation-mode tests (#167): build simulation runs, and drive the /admin
endpoints as the simulation page does

ORM objects are detached after each request (see tests/conftest.ctx), so these take and return ids.
'''
# standard
from datetime import datetime

# pypi
from flask import g

# homegrown
from tm_csv_connector.model import db, User, Simulation, SimulationRun, Result, ScannedBib

TMSIM_ADMIN = 'tmsim-admin@example.com'
TMSIM_USER = 'tmsim-user@example.com'

def user_id(email):
    return User.query.filter_by(email=email).one().id

def login(client, email):
    """log the client in as the user, as Flask-Security's session does"""
    user = User.query.filter_by(email=email).one()
    with client.session_transaction() as s:
        s['_user_id'] = user.fs_uniquifier
        s['_fresh'] = True
    # requests reuse the test's app context (the ctx fixture), so g keeps the user Flask-Login
    # loaded for an earlier request; drop it, so the next request loads this one
    g.pop('_login_user', None)

def make_run(email, name='test simulation', start_time=0.0):
    """a simulation run for the user, of a new simulation; returns the run's id"""
    sim = Simulation(name=name, description='test')
    db.session.add(sim)
    db.session.flush()
    run = SimulationRun(simulation_id=sim.id, user_id=user_id(email), start_time=start_time,
                        timestarted=datetime.now(), score=0)
    db.session.add(run)
    db.session.commit()
    return run.id

def select_run(client, runid):
    """as the simulation page's Run dropdown does"""
    with client.session_transaction() as s:
        s['_results_simulationrun_id'] = str(runid)

def add_sim_results(runid, rows):
    """add results directly, each with its scan, as if the queue had assigned them

    Args:
        runid (int): simulation run
        rows ([(bibno, scan), ...]): result bib (or None) and scanned bib (or None) in place order

    Returns:
        [int]: result ids, in place order
    """
    ids = []
    order = 0
    for place, (bibno, scan) in enumerate(rows, start=1):
        sb = None
        if scan is not None:
            order += 1
            sb = ScannedBib(simulationrun_id=runid, order=order, bibno=scan)
            db.session.add(sb)
        r = Result(simulationrun_id=runid, tmpos=place, place=place, bibno=bibno, time=60.0 * place,
                   is_confirmed=False, scannedbib=sb, had_scannedbib=bool(sb))
        db.session.add(r)
        db.session.flush()
        ids.append(r.id)
    db.session.commit()
    return ids

def sim_post_result(client, runid, pos, secs):
    """as the simulation page does for a Time Machine event; the time is in seconds"""
    resp = client.post('/admin/_simpostresult', json={'opcode': 'primary', 'simulationrun_id': runid,
                                                      'pos': pos, 'time': secs})
    assert resp.status_code == 200
    return resp.get_json()

def sim_post_bib(client, runid, bibno):
    """as the simulation page does for a scan event"""
    resp = client.post('/admin/_simpostbib', json={'opcode': 'scannedbib', 'simulationrun_id': runid, 'bibno': bibno})
    assert resp.status_code == 200
    return resp.get_json()

def sim_poll(client):
    """get the simulation results table as its poll does

    Returns:
        {place: row dict}
    """
    resp = client.get('/admin/resultssim/rest')
    assert resp.status_code == 200, resp.status_code
    return {r['placepos']: r for r in resp.get_json()}

def sim_scan_action(client, action, resultid, scanid):
    resp = client.post('/admin/_simscanaction', data={'action': action, 'resultid': resultid,
                                                      'scanid': 'null' if scanid is None else scanid})
    assert resp.status_code == 200
    return resp.get_json()

def sim_results(runid):
    db.session.expire_all()
    return Result.query.filter_by(simulationrun_id=runid).order_by(Result.place).all()

def sim_queue(runid):
    """(result bib, scanned bib) for each result, in place order"""
    return [(r.bibno, r.scannedbib.bibno if r.scannedbib else None) for r in sim_results(runid)]

def sim_scans(runid):
    db.session.expire_all()
    return [sb.bibno for sb in ScannedBib.query.filter_by(simulationrun_id=runid).order_by(ScannedBib.order)]
