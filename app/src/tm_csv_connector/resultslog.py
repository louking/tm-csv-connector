'''
resultslog - log scans, results, and operator edits on the results view
=========================================================================
Each entry is added to the caller's session, so it's committed (or rolled back) with the
change it describes (#157).
'''
# standard
from datetime import datetime

# pypi
from flask import current_app

# homegrown
from .model import db, ResultsLog

def log_results_event(event, result=None, scannedbib=None, race_id=None, simulationrun_id=None, **fields):
    """add a ResultsLog entry to the session

    the race or simulation run comes from result or scannedbib, unless given explicitly. place and tmpos
    come from result, and scanbibno from scannedbib, unless given in fields

    Args:
        event (str): what happened, e.g., 'result', 'scan', 'use', 'edit'
        result (Result, optional): result the event applies to
        scannedbib (ScannedBib, optional): scanned bib the event applies to
        race_id (int, optional): race, if neither result nor scannedbib is given
        simulationrun_id (int, optional): simulation run, if neither result nor scannedbib is given
        fields: other ResultsLog columns, e.g., old_bibno, new_bibno, info
    """
    source = result or scannedbib
    if source:
        race_id = source.race_id
        simulationrun_id = source.simulationrun_id
    if result:
        fields.setdefault('place', result.place)
        fields.setdefault('tmpos', result.tmpos)
    if scannedbib:
        fields.setdefault('scanbibno', scannedbib.bibno)

    # a log entry with neither would show up nowhere
    if not race_id and not simulationrun_id:
        current_app.logger.warning(f'log_results_event: no race or simulation run for {event} {fields}')
        return

    db.session.add(ResultsLog(time=datetime.now(), event=event,
                              race_id=race_id, simulationrun_id=simulationrun_id, **fields))

def msg_device_time(msg):
    """get the time the client received a message from its device, if the client sent one

    clients before #157, the simulation, and tools/post-test-race.ps1 don't send device_time

    Args:
        msg (dict): message posted by a client

    Returns:
        datetime or None
    """
    value = msg.get('device_time')
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        current_app.logger.warning(f'msg_device_time: ignoring bad device_time {value!r}')
        return None

def commit_results_event(event, **kwargs):
    """log an event and commit it by itself, e.g., after the change it describes was refused or
    rolled back. never raises, so it can't mask the caller's error

    Args: see log_results_event()
    """
    try:
        log_results_event(event, **kwargs)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(f'commit_results_event: could not log {event}')
