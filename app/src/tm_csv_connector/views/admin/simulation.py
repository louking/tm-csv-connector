'''
simulation - simulation views
=================================
'''
# standard
from os.path import join
from os import remove
from uuid import uuid4
from traceback import format_exception_only, format_exc
from csv import DictReader, DictWriter
from datetime import datetime
from requests import post
from re import compile
from json import loads

# pypi
from dominate.tags import div, button, span, select, option, i, input_
from flask import request, jsonify, current_app, url_for, session
from flask_security import current_user
from flask.views import MethodView
from sqlalchemy import update, and_, select as sqlselect
from loutilities.user.tables import DbCrudApiRolePermissions
from loutilities.filters import filtercontainerdiv, filterdiv, yadcfoption
from loutilities.tables import rest_url_for
from loutilities.timeu import timesecs, asctime
from loutilities.tables import DbCrudApi

timedisplay = asctime('%Y-%m-%d %H:%M:%S')

# homegrown
from . import bp
from ...model import User
from ...model import db, Simulation, SimulationEvent, SimulationResult, SimulationRun, SimulationExpected, Result
from ...model import ScannedBib
from ...model import Setting
from ...model import etype_type
from ...times import asc2time, time2asc
from ..common import ResultsView, get_results_posttablehtml, results_dbmapping, results_formmapping, results_validate
from ..common import PostResultApi, PostBibApi, ScanActionApi
from ...fileformat import filecolumns, db2file, filelock, lock, unlock, fulltime

from ...roles import ROLE_SUPER_ADMIN, ROLE_TMSIM_ADMIN
roles_accepted = [ROLE_SUPER_ADMIN, ROLE_TMSIM_ADMIN]

class ParameterError(Exception): pass

class SimConnectorView (DbCrudApi):
    def permission(self):
        session.permanent = True
        
        simulationrun_id = session['_results_simulationrun_id'] if '_results_simulationrun_id' in session else None
        self.simulationrun = SimulationRun.query.filter_by(id=simulationrun_id).one_or_none()
        
        return True


def get_results_filters_sim():
    prehtml = div(_class='simulation-mode')
    
    with prehtml:
        with filtercontainerdiv():
            with div(_class='filter-item'):
                span('Run', _class='label')
                with span(_class='filter'):
                    results_filter_simrun_select = select(id='simulation-run', name="simulation-run", url=url_for('admin._setgetsimulationrun'))
                    # TODO: do we want super-admin to be able to see all simulation runs?
                    simruns = SimulationRun.query.filter_by(user=current_user).order_by(SimulationRun.timestarted.desc()).all()
                    with results_filter_simrun_select:
                        for sr in simruns:
                            option(sr.usersimstart, value=sr.id)
                
                span('Simulation', _class='label')
                with span(_class='filter'):
                    results_filter_sim_select = select(id='sim', name="sim", _class="validate", required='true', aria_required="true", onchange="setParams()")
                    sims = Simulation.query.order_by(Simulation.name).all()
                    with results_filter_sim_select:
                        for s in sims:
                            option(s.name, value=s.id)
            
                span('Start Time', _class='label')
                with span(_class='filter'):
                    input_(id='start-time', name='start-time', type='time', step=.01)
                    
                with span(_class='simulation-controls'):
                    with button(id='start-pause-simulation', _class='filter-item ui-button', title="start simulation", onclick='startPauseSimulation()'):
                        i(id="play-icon", _class="fa-solid fa-play")
                        i(id="pause-icon", _class="fa-solid fa-pause", style="display: none;")
                    with button(id='stop-simulation', _class='filter-item ui-button',  title="stop and record stats", onclick='stopSimulation()'):
                        i(_class="fa-solid fa-stop")
                    with button(id='slow-simulation', _class='filter-item ui-button',  title="run slower", onclick='slowSimulation()'):
                        i(_class="fa-solid fa-backward-fast")
                    with button(id='speed-simulation', _class='filter-item ui-button', title="run faster", onclick='speedSimulation()'):
                        i(_class="fa-solid fa-forward-fast")
                    
                with div(style='display: inline-block; font-weight: bold'):
                    span('1x', id='simulation-speed')
                span('stopped', id='simulation-state', style='font-weight: bold;', _class='label')
                
    return prehtml.render()

class ResultsViewSim(ResultsView, SimConnectorView):
    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        simulationrun_id = session['_results_simulationrun_id'] if '_results_simulationrun_id' in session else None
        self.simulationrun = SimulationRun.query.filter_by(id=simulationrun_id).one_or_none()
        self.queryparams['simulationrun_id'] = simulationrun_id
        # current_app.logger.debug(f'queryparams: {self.queryparams}')

    def set_queue_filters(self):
        """sets queue filters

        Returns:
            boolean: True if caller should update the queued scanned results
        """
        simulationrun_id = session['_results_simulationrun_id'] if '_results_simulationrun_id' in session else None
        simulationrun = SimulationRun.query.filter_by(id=simulationrun_id).one_or_none()
        if simulationrun:
            process_queue = True
            self.result_queue_filter = [Result.simulationrun_id == simulationrun_id]
            self.scannedbib_queue_filter = [ScannedBib.simulationrun_id == simulationrun_id]

        else:
            process_queue = False
            
        return process_queue

    def createrow(self, formdata):
        '''
        creates row in database

        :param formdata: data from create form
        :rtype: returned row for rendering, e.g., from DataTablesEditor.get_response_data()
        '''
        # make sure we record the row's simulationrun id
        formdata['simulationrun_id'] = self.simulationrun.id

        # if edit for previously confirmed entry is done, this will cause the file to be rewritten
        self.check_confirmed(0)

        # remove scanned_bibno as this is readonly
        formdata.pop('scanned_bibno')

        return super().createrow(formdata)

    def updaterow(self, thisid, formdata):
        """if confirm is indicated, confirm all the rows prior to and including this one

        Args:
            thisid (int): id of row to be updated
            formdata (unmutable dict): data from edit form

        Returns:
            row: eturned row for rendering, e.g., from DataTablesEditor.get_response_data()
        
        NOTE: other rows which have been modified will be retrieved in the next polling cycle
        """
        # if edit for previously confirmed entry is done, this will cause the file to be rewritten
        # NOTE: this sets self.result
        self.check_confirmed(thisid)
        
        # remove scanned_bibno as this is readonly
        formdata.pop('scanned_bibno')

        if 'confirm' in formdata and formdata['confirm'] == 'true':
            # LOCK file access
            lock(filelock)
            
            # don't rewrite file when confirming
            self.rewritefile = False

            # set is_confirmed for all rows in this race which have place <= the selected row
            updated = db.session.execute(
                sqlselect(Result)
                .where(and_(
                    Result.simulationrun_id == self.result.simulationrun_id,
                    Result.place <= self.result.place,
                    Result.is_confirmed == False)
                )
                .order_by(Result.place)
            ).all()
            
            # not sure why there is a need to for r[0] -- is this new in sqlalchemy 2.0?
            updated = [r[0] for r in updated]
            
            db.session.execute(
                update(Result)
                .where(Result.id.in_([r.id for r in updated]))
                .values(is_confirmed=True)
            )
            db.session.flush()

            # write the updated results to table
            lastresult = db.session.execute(
                sqlselect(SimulationResult)
                .where(SimulationResult.simulationrun_id == self.simulationrun.id)
                .order_by(SimulationResult.order.desc())
            ).first()
            if lastresult:
                order = lastresult[0].order + 1
            else:
                order = 1
            
            for result in updated:
                simulationresult = SimulationResult(
                    simulationrun_id = self.simulationrun.id,
                    bibno = result.bibno,
                    time = result.time,
                    order = order,
                )
                db.session.add(simulationresult)
                order += 1
            db.session.flush()
                
            # if the simulation is configured to save results to csv file, write the updated results to file
            if current_app.config['SIMULATION_SAVE_CSV']:
                # get output file pathname and write updated results to file
                filesetting = Setting.query.filter_by(name='output-file').one_or_none()
                if filesetting:
                    filepath = join('/output_dir', filesetting.value)

                    # write to the file
                    with open(filepath, mode='a') as f:
                        for result in updated:
                            filedata = db2file(result)
                            current_app.logger.debug(f'appending to {filesetting.value}: {filedata["pos"],filedata["bibno"],filedata["time"]}')
                            csvf = DictWriter(f, fieldnames=filecolumns, extrasaction='ignore')
                            csvf.writerow(filedata)
            
            # UNLOCK file access
            unlock(filelock)
            
            thisrow = self.dte.get_response_data(self.result)
            return thisrow
            
        else:
            return super().updaterow(thisid, formdata)
    

results_view = ResultsViewSim(
    app=bp,  # use blueprint instead of app
    db=db,
    model=Result,
    template='resultssim.jinja2',
    pagename='results',
    endpoint='admin.resultssim',
    rule='/resultssim',
    pretablehtml=get_results_filters_sim,
    posttablehtml=get_results_posttablehtml,
    dbmapping=results_dbmapping,
    formmapping=results_formmapping,
    validate=results_validate,
    idSrc='rowid',
    buttons=lambda: [
        'edit',
        'create',
        'remove',
        'spacer',
        {
            'extend': 'edit',
            'text': 'Confirm',
            'attr': {'id': 'confirm-button'},
            'action': {'eval': 'results_confirm'},
        },
        'spacer',
        'csv', 
    ],
    clientcolumns = [
        {
            'data': 'is_confirmed', 
            'name': 'is_confirmed', 
            'label': '<i class="fa-solid fa-file-circle-check"></i>', 
            'type': 'readonly', 
            'orderable': False,
            'className': 'is_confirmed_field',
            'ed': {'type': 'hidden'},
        },
        {'data': 'placepos', 'name': 'placepos', 'label': 'Place', 'type': 'readonly', 'className': 'placepos_field', 'fieldInfo': 'calculated by the system'},
        {'data': 'tmpos', 'name': 'tmpos', 'label': 'TM Pos', 'orderable': False, 'fieldInfo': 'received from time machine'},
        {
            'data': 'scanned_bibno', 
            'name': 'scanned_bibno', 
            'label': 'Scanned Bib No', 
            'type': 'readonly', 
            'orderable': False,
            'className': 'scanned_bibno_field',
            'ed': {'type': 'hidden'},
        },
        {
            'data': 'bibalert', 
            'name': 'bibalert', 
            'label': '<i class="fa-solid fa-not-equal"></i>', 
            'type': 'readonly', 
            'orderable': False,
            'className': 'bibalert_field',
            'ed': {'type': 'hidden'},
        },
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No', 'orderable': False, 'className': 'bibno_field'},
        {'data': 'time', 'name': 'time', 'label': 'Time', 'orderable': False, 'className': 'time_field'},
        
        # for testing only
        # {'data': 'update_time', 'name': 'update_time', 'label': 'Update Time', 'type': 'readonly'},
    ],
    dtoptions={
        'order': [['placepos:name', 'desc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
results_view.register()


simulation_dbattrs = 'id,name,description'.split(',')
simulation_formfields = 'rowid,name,description'.split(',')
simulation_dbmapping = dict(zip(simulation_dbattrs, simulation_formfields))
simulation_formmapping = dict(zip(simulation_formfields, simulation_dbattrs))

simulation_view = DbCrudApiRolePermissions(
    roles_accepted=roles_accepted,
    app=bp,  # use blueprint instead of app
    db=db,
    model=Simulation,
    template='datatables.jinja2',
    pagename='Simulations',
    endpoint='admin.simulations',
    rule='/simulations',
    dbmapping=simulation_dbmapping,
    formmapping=simulation_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=['create', 'editRefresh', 'remove', 'csv'],
    clientcolumns = [
        {'data': 'name', 'name': 'name', 'label': 'Name',
         },
        {'data': 'description', 'name': 'description', 'label': 'Description',
         },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
simulation_view.register()

simulationevent_dbattrs = 'id,simulation,time,etype,bibno'.split(',')
simulationevent_formfields = 'rowid,simulation,time,etype,bibno'.split(',')
simulationevent_dbmapping = dict(zip(simulationevent_dbattrs, simulationevent_formfields))
simulationevent_formmapping = dict(zip(simulationevent_formfields, simulationevent_dbattrs))
simulationevent_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
simulationevent_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)

def simulationevent_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
            i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('simulationevent-external-filter-simulation', 'Simulation')
    return pretablehtml.render()

simulationevent_yadcf_options = [
    yadcfoption('simulation.name:name', 'simulationevent-external-filter-simulation', 'select', placeholder='Select simulation', width='300px', select_type='select2'),
]

simulationevent_view = DbCrudApiRolePermissions(
    roles_accepted=roles_accepted,
    app=bp,  # use blueprint instead of app
    db=db,
    model=SimulationEvent,
    template='datatables.jinja2',
    pretablehtml=simulationevent_filters,
    yadcfoptions=simulationevent_yadcf_options,
    pagename='Simulation Events',
    endpoint='admin.simulationevents',
    rule='/simulationevents',
    dbmapping=simulationevent_dbmapping,
    formmapping=simulationevent_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=lambda: ['create', 'editRefresh', 'remove', 'csv',
        {
            'extend': 'create',
            'text': 'Import',
            'name': 'import-simulationevents',
            'editor': {'eval': 'simulationevents_import_saeditor.saeditor'},
            'url': url_for('admin._simulationevents'),
            'action': {
                'eval': f'simulationevents_import("{url_for('admin._simulationevents')}")'
            }
        },
    ],
    clientcolumns = [
        {'data': 'simulation', 'name': 'simulation', 'label': 'Simulation',
         'className': 'field_req',
         '_treatment': {
             'relationship': {'fieldmodel': Simulation, 'labelfield': 'name',
                             'formfield': 'simulation',
                             'dbfield': 'simulation',
                             'uselist': False,
                             }}
         },
        {'data': 'time', 'name': 'time', 
         'className': 'field_req',
         'label': 'Time'},
        {'data': 'etype', 'name': 'etype', 'label': 'Type',
         'className': 'field_req',
         'type': 'select2',
         'options': etype_type,
        },
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No'},
    ],
    dtoptions={
        'order': [['simulation.name:name', 'asc'], ['time:name', 'asc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
simulationevent_view.register()

class SimulationEventsApi(MethodView):
    """upload simulation events from file

    Raises:
        ParameterError: error if action is not 'upload' or 'edit', or if bad file format detected
    """
    ALLOWED_EXTENSIONS = ['csv', 'txt']
    
    def get(self):
        # this returns initial values for the form, should be empty because the
        # input form doesn't have any initial values
        return jsonify({})
    
    def allowed_filename(self, filename):
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def import_csv_file(self, filepath, simid):
        """import csv file and save list of SimulationEvent objects

        Args:
            filepath (str): path to the csv file
            simid (int): simulation id to associate with the events
        """
        with open(filepath, newline='') as stream:
            csvfile = DictReader(stream)
            header = csvfile.fieldnames
            # check for required fields
            if 'time' not in header or 'etype' not in header or 'bibno' not in header:
                raise ParameterError('missing required field')
            
            # delete all existing events for this simulation
            db.session.query(SimulationEvent).filter(SimulationEvent.simulation_id == simid).delete()
            
            # read to end of file
            lineno = 1  # skip header
            for line in csvfile:
                lineno += 1
                # check for valid etype
                if line['etype'] not in etype_type:
                    raise ParameterError(f"line {lineno}: invalid etype '{line['etype']}'")
                if line['etype'] == 'scan':
                    # check for bibno
                    if not line['bibno']:
                        raise ParameterError(f"line {lineno}: etype 'scan' requires bibno")
                
                # create new SimulationEvent object
                simevent = SimulationEvent(
                    simulation_id = simid,
                    time = timesecs(line['time']),
                    etype = line['etype'],
                    bibno = line['bibno'],
                )
                db.session.add(simevent)

    def import_log_file(self, filepath, simid):
        """import tmtility log file and save list of SimulationEvent objects

        Args:
            filepath (str): log file path with txt extension
            simid (int): Simulation id to associate with the events
        """
        
        recdata = compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[\d{4}-\d{2}-\d{2} (?P<time>\d{2}:\d{2}:\d{2},\d{3})\].*received data (?P<cmd>\{.*\})")
        
        with open(filepath) as stream:
            lineno = 0
            for line in stream:
                lineno += 1
                
                recdata_match = recdata.match(line) # received data
                
                if recdata_match:
                    timestamp_a = recdata_match.group('time')
                    timestamp_a = timestamp_a.replace(',', '.')  # replace comma with dot for float conversion
                    timestamp = timesecs(timestamp_a)  # convert to seconds
                    
                    # skip logs before race start
                    if timestamp < self.start_time:
                        continue
                    
                    # parse the command
                    cmd_a = recdata_match.group('cmd')
                    cmd_a = cmd_a.replace("'", '"')  # replace single quotes with double quotes for json conversion
                    cmd = loads(cmd_a)  # parse as json
                    
                    match cmd['opcode']:
                        # time machine result with select
                        case 'select':
                            etype = 'timemachine'
                            bibno = cmd['bibno']
                            time = timesecs(cmd['time'])
                        
                        # time machine result without select
                        case 'primary':
                            etype = 'timemachine'
                            bibno = None
                            time = timesecs(cmd['time'])
                        
                        # bib number from scanner
                        case 'scannedbib':
                            etype = 'scan'
                            bibno = cmd['bibno']
                            time = timestamp - self.start_time
                            
                    # create new SimulationEvent object
                    simevent = SimulationEvent(
                        simulation_id = simid,
                        time = time,
                        etype = etype,
                        bibno = bibno,
                    )
                    db.session.add(simevent)
                    

    def post(self):
        try:
            options = request.form
            action = options['action']
            if action == 'upload':
                if 'upload' not in request.files:
                    return jsonify(status='fail', error='no upload')
                thisfile = request.files['upload']
                fname = thisfile.filename
                # if the user does not select a file, the browser submits an empty file without a filename
                if fname == '':
                    return jsonify(status='fail', error='no selected file')
                if not self.allowed_filename(fname):
                    return jsonify(status='fail', error=f'must have extension in {self.ALLOWED_EXTENSIONS}')
                
                # save file for later processing (adapted from loutilities.tablefiles.FieldUpload)
                fid = uuid4().hex
                ext = fname.rsplit('.', 1)[1].lower()
                fidfname = f'{fid}.{ext}'
                filepath = join('/tmp', fidfname)
                thisfile.save(filepath)
                
                returndata = {
                    'upload' : {'id': fidfname },
                    'files' : {
                        'data' : {
                            fidfname : {'filename': thisfile.filename}
                        },
                    },
                }
                return jsonify(**returndata)
            
            # this handles Import button
            elif action == 'edit':
                simid = request.form['data[keyless][simulation]']
                force = request.form['data[keyless][force]']
                
                # start time only used for log file import
                self.start_time = (timesecs(request.form['data[keyless][start_time]']) 
                                   if 'data[keyless][start_time]' in request.form and request.form['data[keyless][start_time]'] 
                                   else 0)

                if not simid:
                    return jsonify(status='fail', error='please choose a simulation')
            
                # if there are already simulation events exist, verify user wants to overwrite
                thesesimevents = SimulationEvent.query.filter_by(simulation_id=simid).all()
                if thesesimevents and not force=='true':
                    db.session.rollback()
                    return jsonify(status='fail', cause='Overwrite events?', confirm=True)

                # user has confirmed overwrite, so delete existing events for this simulation
                SimulationEvent.query.filter_by(simulation_id=simid).delete()
                
                filepath = join('/tmp', request.form['data[keyless][file]'])
                ext = filepath.rsplit('.', 1)[1].lower()
                
                if ext == 'csv':
                    # import csv file
                    self.import_csv_file(filepath, simid)
                
                elif ext == 'txt':
                    # import tmtility log (txt) file
                    self.import_log_file(filepath, simid)
                    
                else:
                    raise ParameterError(f"unsupported file extension '{ext}'")

                # commit changes to database, delete temporary file, and declare success
                db.session.commit()
                remove(filepath)
                return jsonify(status='success')
            
            else:
                raise ParameterError('invalid action')

        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
simulationevents_api = SimulationEventsApi.as_view('_simulationevents')
bp.add_url_rule('/_simulationevents', view_func=simulationevents_api, methods=['POST','GET'])


simulationexpected_dbattrs = 'id,simulation,order,time,epsilon,bibno'.split(',')
simulationexpected_formfields = 'rowid,simulation,order,time,epsilon,bibno'.split(',')
simulationexpected_dbmapping = dict(zip(simulationexpected_dbattrs, simulationexpected_formfields))
simulationexpected_formmapping = dict(zip(simulationexpected_formfields, simulationexpected_dbattrs))
simulationexpected_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
simulationexpected_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)

def simulationexpected_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
            i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('simulationexpected-external-filter-simulation', 'Simulation')
    return pretablehtml.render()

simulationexpected_yadcf_options = [
    yadcfoption('simulation.name:name', 'simulationexpected-external-filter-simulation', 'select', placeholder='Select simulation', width='300px', select_type='select2'),
]


simulationexpected_view = DbCrudApiRolePermissions(
    roles_accepted=roles_accepted,
    app=bp,  # use blueprint instead of app
    db=db,
    model=SimulationExpected,
    template='datatables.jinja2',
    pretablehtml=simulationexpected_filters(),
    yadcfoptions=simulationexpected_yadcf_options,
    pagename='Simulation Expected Results',
    endpoint='admin.simulationexpected',
    rule='/simulationexpected',
    dbmapping=simulationexpected_dbmapping,
    formmapping=simulationexpected_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=lambda: ['create', 'editRefresh', 'remove', 'csv',
        {
            'extend': 'create',
            'text': 'Import',
            'name': 'import-simulationexpected',
            'editor': {'eval': 'simulationexpected_import_saeditor.saeditor'},
            'url': url_for('admin._simulationexpected'),
            'action': {
                'eval': f'simulationexpected_import("{url_for('admin._simulationexpected')}")'
            }
        },
    ],
    clientcolumns = [
        {'data': 'simulation', 'name': 'simulation', 'label': 'Simulation',
         'className': 'field_req',
         '_treatment': {
             'relationship': {'fieldmodel': Simulation, 'labelfield': 'name',
                             'formfield': 'simulation',
                             'dbfield': 'simulation',
                             'uselist': False,
                             }}
         },
        {'data': 'order', 'name': 'order', 'label': 'Order'},
        {'data': 'bibno', 
         'className': 'field_req',
         'name': 'bibno', 
         'label': 'Bib No'},
        {'data': 'time', 'name': 'time', 
         'className': 'field_req',
         'label': 'Time'},
        {'data': 'epsilon', 'name': 'epsilon', 
         'className': 'field_req',
         'label': 'Epsilon',
         'fieldInfo': 'if non-zero, bibno match within epsilon seconds of expected time',
         'ed': {'def': 0},
         },
    ],
    dtoptions={
        'order': [['simulation.name:name', 'asc'],['order:name', 'asc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
simulationexpected_view.register()

class SimulationExpectedApi(MethodView):
    """upload simulation expected from file

    Raises:
        ParameterError: error if action is not 'upload' or 'edit', or if bad file format detected
    """
    ALLOWED_EXTENSIONS = ['csv']
    
    def get(self):
        # this returns initial values for the form, should be empty because the
        # input form doesn't have any initial values
        return jsonify({})
    
    def allowed_filename(self, filename):
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def post(self):
        lineno = 0
        try:
            options = request.form
            action = options['action']
            if action == 'upload':
                if 'upload' not in request.files:
                    return jsonify(status='fail', error='no upload')
                thisfile = request.files['upload']
                fname = thisfile.filename
                # if the user does not select a file, the browser submits an empty file without a filename
                if fname == '':
                    return jsonify(status='fail', error='no selected file')
                if not self.allowed_filename(fname):
                    return jsonify(status='fail', error=f'must have extension in {self.ALLOWED_EXTENSIONS}')
                
                # save file for later processing (adapted from loutilities.tablefiles.FieldUpload)
                fid = uuid4().hex
                ext = fname.rsplit('.', 1)[1].lower()
                fidfname = f'{fid}.{ext}'
                filepath = join('/tmp', fidfname)
                thisfile.save(filepath)
                
                returndata = {
                    'upload' : {'id': fidfname },
                    'files' : {
                        'data' : {
                            fidfname : {'filename': thisfile.filename}
                        },
                    },
                }
                return jsonify(**returndata)
            
            # this handles Import button
            elif action == 'edit':
                simid = request.form['data[keyless][simulation]']
                force = request.form['data[keyless][force]']
                
                if not simid:
                    return jsonify(status='fail', error='please choose a simulation')
            
                # if there are already simulation events exist, verify user wants to overwrite
                thesesimexpected = SimulationExpected.query.filter_by(simulation_id=simid).all()
                if thesesimexpected and not force=='true':
                    db.session.rollback()
                    return jsonify(status='fail', cause='Overwrite expected results?', confirm=True)

                filepath = join('/tmp', request.form['data[keyless][file]'])
                with open(filepath, newline='') as stream:
                    csvfile = DictReader(stream)
                    header = csvfile.fieldnames
                    # check for required fields
                    if 'order' not in header or 'time' not in header or 'bibno' not in header:
                        raise ParameterError('missing required field')
                    
                    # delete all existing expected entries for this simulation
                    db.session.query(SimulationExpected).filter(SimulationExpected.simulation_id == simid).delete()
                    
                    # read to end of file
                    lineno = 1  # skip header
                    for line in csvfile:
                        lineno += 1
                        
                        # create new SimulationExpected object
                        simexpected = SimulationExpected(
                            simulation_id = simid,
                            order = line['order'],
                            time = timesecs(line['time']),
                            bibno = line['bibno'],
                            epsilon = line['epsilon'] if 'epsilon' in line and line['epsilon'] else 0,
                        )
                        db.session.add(simexpected)
                        
                # commit changes to database, delete temporary file, and declare success
                db.session.commit()
                remove(filepath)
                return jsonify(status='success')
            
            else:
                raise ParameterError('invalid action')

        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            if lineno:
                output_result = {'status' : 'fail', 'error': f'exception occurred processing line {lineno}:<br>{exc}'}
            else:
                output_result = {'status' : 'fail', 'error': f'exception occurred:<br>{exc}'}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
simulationexpected_api = SimulationExpectedApi.as_view('_simulationexpected')
bp.add_url_rule('/_simulationexpected', view_func=simulationexpected_api, methods=['POST','GET'])


# note user.name and simulation.name are used rather than _treatment/relationship as this is a read only view
simulationrun_dbattrs = 'id,user.name,simulation.name,start_time,timestarted,timeended,score'.split(',')
simulationrun_formfields = 'rowid,user,simulation,timestarted,start_time,timeended,score'.split(',')
simulationrun_dbmapping = dict(zip(simulationrun_dbattrs, simulationrun_formfields))
simulationrun_formmapping = dict(zip(simulationrun_formfields, simulationrun_dbattrs))
simulationrun_dbmapping['start_time'] = lambda formrow: timesecs(formrow['start_time']) if formrow['start_time'] else None
simulationrun_formmapping['start_time'] = lambda dbrow: fulltime(dbrow.start_time) if dbrow.start_time else ''
simulationrun_dbmapping['timestarted'] = lambda formrow: timedisplay.asc2dt(formrow['timestarted']) if formrow['timestarted'] else None
simulationrun_formmapping['timestarted'] = lambda dbrow: timedisplay.dt2asc(dbrow.timestarted) if dbrow.timestarted else ''
simulationrun_dbmapping['timeended'] = lambda formrow: timedisplay.asc2dt(formrow['timeended']) if formrow['timeended'] else None
simulationrun_formmapping['timeended'] = lambda dbrow: timedisplay.dt2asc(dbrow.timeended) if dbrow.timeended else ''

def simulationrun_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
            i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('simulationrun-external-filter-user', 'User')
        filterdiv('simulationrun-external-filter-simulation', 'Simulation')
    return pretablehtml.render()

simulationrun_yadcf_options = [
    yadcfoption('user:name', 'simulationrun-external-filter-user', 'select', placeholder='Select user', width='300px', select_type='select2'),
    yadcfoption('simulation:name', 'simulationrun-external-filter-simulation', 'select', placeholder='Select simulation', width='300px', select_type='select2'),
]

simulationrun_view = DbCrudApiRolePermissions(
    roles_accepted=roles_accepted,
    app=bp,  # use blueprint instead of app
    db=db,
    model=SimulationRun,
    template='datatables.jinja2',
    pretablehtml=simulationrun_filters(),
    yadcfoptions=simulationrun_yadcf_options,
    pagename='Simulation Run',
    endpoint='admin.simulationruns',
    rule='/simulationruns',
    dbmapping=simulationrun_dbmapping,
    formmapping=simulationrun_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=['csv'],
    clientcolumns = [
        {'data': 'user', 'name': 'user', 'label': 'User'},
        {'data': 'simulation', 'name': 'simulation', 'label': 'Simulation'},
        {'data': 'start_time', 'name': 'start_time', 'label': 'Race Start Time'},
        {'data': 'timestarted', 'name': 'timestarted', 'label': 'Time Started'},
        {'data': 'timeended', 'name': 'timeended', 'label': 'Time Ended'},
        {'data': 'score', 'name': 'score', 'label': 'Score'},
    ],
    dtoptions={
        'order': [['user:name', 'asc'],['simulation:name', 'asc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
simulationrun_view.register()

class CreateGetSimulationRunApi(MethodView):
    """create simulation run and return select option and next step
    This is used by the simulation run start button in the simulation view.

    """
    def permission(self):
        session.permanent = True
        
        # check if user is authenticated
        if not current_user.is_authenticated:
            return False
        
        # check if user has role
        if not current_user.has_role(ROLE_TMSIM_ADMIN) and not current_user.has_role(ROLE_SUPER_ADMIN):
            current_app.logger.warning(f'User {current_user.id} tried to access simulation run creation without permission')
            return False
        
        # check if simulation exists
        sim_id = request.form.get('simulation_id', None)
        if not sim_id:
            current_app.logger.warning(f'Logic error: simulation_id is not provided in request form')
            return False
        
        sim = Simulation.query.filter_by(id=sim_id).one_or_none()
        if not sim:
            current_app.logger.warning(f'Logic error: simulation {sim_id} not found in simuation table')
            return False
        
        return True
    
    def post(self):
        # this creates a new simulation run and returns the select option
        try:
            if not self.permission():
                raise ParameterError('permission denied')
            
            sim_id = request.form.get('simulation_id', None)
            if not sim_id:
                return jsonify({'status': 'fail', 'error': 'simulation_id is required'})
            sim = Simulation.query.get(sim_id)
            if not sim:
                return jsonify({'status': 'fail', 'error': f'simulation {sim_id} not found'})
            user_id = current_user.id
            a_start_time = request.form.get('start_time', None)
            if not a_start_time:
                return jsonify({'status': 'fail', 'error': 'Start Time is required'})
            start_time = timesecs(a_start_time) if a_start_time else 0
            simrun = SimulationRun(
                user_id = user_id,
                simulation_id = sim_id,
                start_time = start_time,
                timestarted = datetime.now(),
                timeended = None,   # this will be set when the run is completed
                score = 0,          # this will be set when the run is completed
            )
            db.session.add(simrun)
            db.session.flush()
            
            options = [{'value': sr.id, 'label': sr.usersimstart} 
                       for sr in db.session.query(SimulationRun).filter(SimulationRun.user_id == user_id).order_by(SimulationRun.timestarted.desc()).all()]
            
            # initialize simulation run next step
            # this is the first simulation event, which is the start of the simulation
            simstepsdb = db.session.query(SimulationEvent).filter(SimulationEvent.simulation_id == sim_id).order_by(SimulationEvent.time).all()
            
            simsteps = []
            tmpos = 1
            for s in simstepsdb:
                # create a dictionary for each simulation step
                step = {
                    'id': s.id,
                    'time': s.time,
                    'etype': s.etype,
                    'bibno': s.bibno
                }
                if s.etype == 'timemachine':
                    # add tmpos to step
                    step['tmpos'] = tmpos
                    tmpos += 1
                simsteps.append(step)
            
            returns = {'status': 'success',
                       'simsteps': simsteps,
                       'options': options}
            
            db.session.commit()
            return jsonify(returns)
    
        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
creategetsimulationrun_api = CreateGetSimulationRunApi.as_view('_setgetsimulationrun')
bp.add_url_rule('/_creategetsimulationrun', view_func=creategetsimulationrun_api, methods=['POST'])

class SimStepApi(MethodView):
    """execute simulation step

    """
    def permission(self):
        session.permanent = True
        
        # check if user is authenticated
        if not current_user.is_authenticated:
            return False
        
        # check if user has role
        if not current_user.has_role(ROLE_TMSIM_ADMIN) and not current_user.has_role(ROLE_SUPER_ADMIN):
            current_app.logger.warning(f'User {current_user.id} tried to access simulation run creation without permission')
            return False
        
        self.simrun_id = request.form.get('simulationrun_id', None)
        if not self.simrun_id:
            current_app.logger.warning('simulationrun_id is required')
            return False
        
        simrun = db.session.query(SimulationRun).filter_by(id=self.simrun_id).one_or_none()
        if not simrun:
            current_app.logger.warning(f'simulation run {self.simrun_id} not found')
            return False
        
        return True
    
    def post(self):
        # this executes a simulation step
        try:
            if not self.permission():
                raise ParameterError('permission denied')
            
            # execute simulation step
            
            etype = request.form.get('step[etype]', None)
            if not etype:
                return jsonify({'status': 'fail', 'error': 'etype is required'})
            
            time = request.form.get('step[time]', None)
            if not time:
                return jsonify({'status': 'fail', 'error': 'time is required'})
                
            # bibno is optional, but required for etype 'scan'
            bibno = request.form.get('step[bibno]', None)
            
            # tmpos is optional, but required for etype 'timemachine'
            tmpos = request.form.get('step[tmpos]', None)
    
            if etype not in etype_type:
                return jsonify({'status': 'fail', 'error': f'etype {etype} is not valid'})
            
            
            # headers are needed for flask to see the correct server URL
            headers = dict(request.headers)
            headers.pop('Content-Type', None)
            headers.pop('Content-Length', None)

            # need to go back out to the docker host to call the admin endpoints
            if etype == 'scan':
                url = f'http://host.docker.internal:{request.headers['X-Forwarded-Port']}{url_for('admin._simpostbib')}'
                if not bibno:
                    return jsonify({'status': 'fail', 'error': 'bibno is required for etype scan'})
                rsp = post(url, headers=headers, json={'opcode': 'scannedbib', 'bibno': bibno, 'simulationrun_id': self.simrun_id})
            
            elif etype == 'timemachine':
                url = f'http://host.docker.internal:{request.headers['X-Forwarded-Port']}{url_for('admin._simpostresult')}'
                if not tmpos:
                    return jsonify({'status': 'fail', 'error': 'tmpos is required for etype timemachine'})
                if not bibno:
                    rsp = post(url, headers=headers, json={'opcode': 'primary', 'simulationrun_id': self.simrun_id, 'time': time, 'pos': tmpos})
                else:
                    rsp = post(url, headers=headers, json={'opcode': 'select',  'simulationrun_id': self.simrun_id, 'time': time, 'pos': tmpos, 'bibno': bibno})
            
            return jsonify({'status': 'success'})
    
        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
simstep_api = SimStepApi.as_view('_simstep')
bp.add_url_rule('/_simstep', view_func=simstep_api, methods=['POST'])

# adapted from https://g.co/gemini/share/f7cc51f83809
def group_results_by_bibno(results_list):
    """Groups results by bibno, handling duplicate bibs."""
    grouped = {}
    for entry in results_list:
        bibno = entry.bibno
        time = entry.time
        if bibno not in grouped:
            grouped[bibno] = []
        grouped[bibno].append({time: entry})
    return grouped

def compare_sim_results_with_expected(expected_results, sim_results):
    """
    Compares two lists of race results, handling potential duplicate bib numbers.

    Args:
        expected_results: A list of dicts with 'bibno' and 'time'.
        sim_results: A list of dicts with 'bibno' and 'time'.

    Returns:
        A dictionary containing all discrepancies.
    """
    discrepancies = {
        'time_mismatches': [],
        'missing_from_sim': [],
        'extra_in_sim': [],
        # 'order_errors': []
    }

    # Group results by bibno to handle duplicates
    expected_grouped = group_results_by_bibno(expected_results)
    sim_grouped = group_results_by_bibno(sim_results)

    # Compare entries and identify mismatches and missing bibs
    for bibno, expected_times in expected_grouped.items():
        expected_time_dict = expected_times[0]  # assumes only one expected for this bibno
        expected_time = list(expected_time_dict.keys())[0]
        if bibno in sim_grouped:
            sim_times = sim_grouped[bibno]
            current_app.logger.debug(f'sim_times={sim_times}, expected_time={expected_time}, epsilon={expected_time_dict[expected_time].epsilon}')

            for sim_time_dict in sim_times:
                sim_time = list(sim_time_dict.keys())[0]
                if abs(sim_time - expected_time) <= expected_time_dict[expected_time].epsilon:
                    sim_time_dict[sim_time].correct = True
                else:
                    sim_time_dict[sim_time].correct = False
                    discrepancies['time_mismatches'].append({
                        'bibno': bibno,
                        'expected_time': expected_time,
                        'sim_time': sim_time
                    })
            # Remove from sim_grouped to track 'extra' entries later
            del sim_grouped[bibno]
        else:
            discrepancies['missing_from_sim'].append({'bibno': bibno, 'expected_times': expected_times})

    # Any remaining entries in sim_grouped are 'extra' bibs
    for bibno, times in sim_grouped.items():
        discrepancies['extra_in_sim'].append({'bibno': bibno, 'sim_times': times})
        for sim_time in times:
            times[sim_time].correct = False

    # # Check for order errors
    # expected_bibnos = [entry.bibno for entry in expected_results]
    # sim_bibnos = [entry.bibno for entry in sim_results]
    #
    # if expected_bibnos != sim_bibnos:
    #     discrepancies['order_errors'].append({
    #         'message': 'Simulation results are not in the same order as expected.',
    #         'expected_order': expected_bibnos,
    #         'sim_order': sim_bibnos
    #     })

    return discrepancies

class SimFinishApi(MethodView):
    """finish simulation run and calculate score

    """
    def permission(self):
        session.permanent = True
        
        # check if user is authenticated
        if not current_user.is_authenticated:
            return False
        
        # check if user has role
        if not current_user.has_role(ROLE_TMSIM_ADMIN) and not current_user.has_role(ROLE_SUPER_ADMIN):
            current_app.logger.warning(f'User {current_user.id} tried to access simulation run creation without permission')
            return False
        
        self.simrun_id = request.form.get('simulationrun_id', None)
        if not self.simrun_id:
            current_app.logger.warning('simulationrun_id is required')
            return False
        
        self.simrun = db.session.query(SimulationRun).filter_by(id=self.simrun_id).one_or_none()
        if not self.simrun:
            current_app.logger.warning(f'simulation run {self.simrun_id} not found')
            return False
        
        return True
    
    def post(self):
        # this finishes a simulation run
        try:
            if not self.permission():
                raise ParameterError('permission denied')
            
            # get simulation run results
            simrun_results = db.session.query(SimulationResult).filter(SimulationResult.simulationrun_id == self.simrun.id).order_by(SimulationResult.order).all()
            num_results = len(simrun_results)
            
            # get expected results
            simulation_id = self.simrun.simulation_id
            expected_results = db.session.query(SimulationExpected).filter(SimulationExpected.simulation_id == simulation_id).order_by(SimulationExpected.order).all()
            num_expected = len(expected_results)
            
            discrepancies = compare_sim_results_with_expected(expected_results, simrun_results)
            # for debugging
            current_app.logger.debug(f'Simulation run {self.simrun.userstart} discrepancies: {discrepancies}, num_results={num_results}, num_expected={num_expected}')
            
            # calculate score
            num_errors = len(discrepancies['time_mismatches']) + len(discrepancies['missing_from_sim']) + len(discrepancies['extra_in_sim'])
            divisor = max(num_expected, num_results)
            num_correct = divisor - num_errors if divisor > num_errors else 0
            self.simrun.score = (num_correct / divisor) * 100 if divisor > 0 else 0
            self.simrun.timeended = datetime.now()
            db.session.commit()
            
            return jsonify({'status': 'success', 'score': f'{round(self.simrun.score)}%', })
    
        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
simfinish_api = SimFinishApi.as_view('_simfinish')
bp.add_url_rule('/_simfinish', view_func=simfinish_api, methods=['POST'])

class SimPostResultApi(PostResultApi):
    def set_query(self):
        """initializes query parameters to retrieve Result records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        """
        msg = request.json
        
        return ([Result.simulationrun_id == msg['simulationrun_id']])
    
    def new_result(self):
        """format a Result record, setting time, simulationrun_id
        other fields are set by the PostResultApi post method

        Returns:
            Result()
        """
        msg = request.json

        result = Result()
        # simulated result time comes in float format, different from time machine formatting
        result.time = float(msg['time'])
        result.simulationrun_id = msg['simulationrun_id']
        return result

simpostresult_api = SimPostResultApi.as_view('_simpostresult')
bp.add_url_rule('/_simpostresult', view_func=simpostresult_api, methods=['POST',])


class SimPostBibApi(PostBibApi):
    def set_query(self):
        """initializes query parameters to retrieve ScannedBib records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        """
        msg = request.json
        
        return ([ScannedBib.simulationrun_id == msg['simulationrun_id']])
    
    def new_scannedbib(self):
        """format a ScannedBib record

        Returns:
            ScannedBib()
        """
        msg = request.json

        scannedbib = ScannedBib()
        scannedbib.simulationrun_id = msg['simulationrun_id']

        return scannedbib
    
simpostbib_api = SimPostBibApi.as_view('_simpostbib')
bp.add_url_rule('/_simpostbib', view_func=simpostbib_api, methods=['POST',])


simulationresult_dbattrs = 'id,time,bibno,order,correct,simulationrun.usersimstart'.split(',')
simulationresult_formfields = 'rowid,time,bibno,order,correct,usersimstart'.split(',')
simulationresult_dbmapping = dict(zip(simulationresult_dbattrs, simulationresult_formfields))
simulationresult_formmapping = dict(zip(simulationresult_formfields, simulationresult_dbattrs))
simulationresult_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
simulationresult_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)

def simulationresult_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
            i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('simulationresult-external-filter-simulationrun', 'Run')
    return pretablehtml.render()

simulationresult_yadcf_options = [
    yadcfoption('usersimstart:name', 'simulationresult-external-filter-simulationrun', 'select', placeholder='Select run', width='300px', select_type='select2'),
]

simulationresult_view = DbCrudApiRolePermissions(
    roles_accepted=roles_accepted,
    app=bp,  # use blueprint instead of app
    db=db,
    model=SimulationResult,
    template='datatables.jinja2',
    pretablehtml=simulationresult_filters(),
    yadcfoptions=simulationresult_yadcf_options,
    pagename='Simulation Run Results',
    endpoint='admin.simulationresults',
    rule='/simulationresults',
    dbmapping=simulationresult_dbmapping,
    formmapping=simulationresult_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=['csv'],
    clientcolumns = [
        {'data': 'usersimstart', 'name': 'usersimstart', 'label': 'User Sim Start'},
        {'data': 'order', 'name': 'order', 'label': 'Order'},
        {'data': 'time', 'name': 'time', 'label': 'Time'},
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No'},
        {'data': 'correct', 'name': 'correct', 'label': 'Correct'},
    ],
    dtoptions={
        'order': [['usersimstart:name', 'desc'],['order:name', 'asc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
simulationresult_view.register()


class GetSimulationsApi(MethodView):
    """get simulations for select field
    """
    def get(self):
        options = []
        # sort most recent race first
        simulations = Simulation.query.order_by(Simulation.name.asc()).all()
        for s in simulations:
            option = {'value': s.id, 'label': s.name}
            options.append(option)
        
        return jsonify(options)

getsimulations_api = GetSimulationsApi.as_view('_getsimulations')
bp.add_url_rule('/_getsimulations', view_func=getsimulations_api, methods=['GET'])

class SimScanActionApi(ScanActionApi):
    def get_source(self, result):
        """initialize source item to use for filtering
        
        Arts:
            result (object): result item to use for filtering
            
        Returns:
            source item, suitable for .filter(source==source)

        """
        return result.simulationrun
    
    def get_source_dict(self, source):
        """initializes source dictionary
        
        Args:
            source (object): source item to use for filtering
            
        Returns:
            {source dict}, suitable for .filter_by(**self.get_source_dict()) or 

        """
        return {'simulationrun': source}

scanaction_api = SimScanActionApi.as_view('_simscanaction')
bp.add_url_rule('/_simscanaction', view_func=scanaction_api, methods=['POST',])
