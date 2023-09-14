'''
home - public views
=================================
'''
# standard
from datetime import timedelta
from traceback import format_exception_only, format_exc
from os.path import join
from shutil import copy
from csv import DictWriter

# pypi
from flask import g, render_template, session, request, current_app, jsonify
from flask.views import MethodView
from loutilities.tables import DbCrudApi
from loutilities.timeu import asctime, timesecs
from dominate.tags import div, button, span, select, option, p
from loutilities.filters import filtercontainerdiv

# homegrown
from . import bp
from ...model import db, Race, Result, Setting
from ...fileformat import filecolumns, db2file, filelock

class ParameterError(Exception): pass

dtrender = asctime('%Y-%m-%d')
sincerender = asctime('%Y-%m-%dT%H:%M:%S%z')

class TmConnectorView (DbCrudApi):
    def permission(self):
        race_id = session['_results_raceid'] if '_results_raceid' in session else None
        self.race = Race.query.filter_by(id=race_id).one_or_none()
        return True

class Home(MethodView):

    def get(self):
        return render_template('home.jinja2',
                               pagename='Home',
                               )

home_view = Home.as_view('home')
bp.add_url_rule('/', view_func=home_view, methods=['GET',])

    
# adapted from https://github.com/aiordache/demos/blob/c7aa37cc3e2f8800296f668138b4cf208b27380a/dockercon2020-demo/app/src/server.py
# similar to https://github.com/docker/awesome-compose/blob/e6b1d2755f2f72a363fc346e52dce10cace846c8/nginx-flask-mysql/backend/hello.py

def asc2time(asctime):
    return timesecs(asctime)

def time2asc(dbtime):
    timestr = str(timedelta(seconds=dbtime))
    wholefrac = timestr.split('.')
    if len(wholefrac) == 1:
        wholefrac.append('0')
    whole, frac = wholefrac
    frac = f'{round(int(frac)/10000):02}'
    return '.'.join([whole, frac])

results_dbattrs = 'id,tmpos,place,bibno,time,race_id,update_time'.split(',')
results_formfields = 'rowid,tmpos,placepos,bibno,time,race_id,update_time'.split(',')
results_dbmapping = dict(zip(results_dbattrs, results_formfields))
results_formmapping = dict(zip(results_formfields, results_dbattrs))
results_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
results_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)

def get_results_filters():
    prehtml = div()
    results_filters = filtercontainerdiv()
    prehtml += results_filters
    results_filters += div(button("placeholder", id="connect-disconnect", _class='filter-item'), _class='filter')
    results_filter_race = div(_class='filter-item')
    results_filters += results_filter_race
    with results_filter_race:
        span('Race', _class='label')
        with span(_class='filter'):
            results_filter_race_select = select(id='race', name="race", _class="validate", required='true', aria_required="true", onchange="setParams()")
            races = Race.query.order_by(Race.date.desc()).all()
            # select first (lastest) race
            selected = False
            with results_filter_race_select:
                for r in races:
                    if not selected:
                        option(r.raceyear, value=r.id, selected='true')
                        selected = True
                    else:
                        option(r.raceyear, value=r.id)
    results_filter_port = div(_class='filter-item')
    results_filters += results_filter_port
    with results_filter_port:
        span('Port', _class='label')
        with span(_class='filter'):
            with select(id='port', name="port", _class="validate", required='true', aria_required="true", onchange="setParams()"):
                for port in ['COM3', 'COM4', 'COM8']:
                    if '_results_port' in session and port == session['_results_port']:
                        option(port, selected='true')
                    else:
                        option(port)
    updates_suspended_warning = div()
    prehtml += updates_suspended_warning
    with updates_suspended_warning:
        p('display updates suspended - deselect to resume', id='updates-suspended', style='color: white; font-weight: bold; background-color: red; text-align: center; display: none;')
    return prehtml.render()

def results_validate(action, formdata):
    results = []
    from re import compile
    
    timepattern = compile('^(\d{1,2}:)?([0-5]\d:)?[0-5]\d(\.\d{0,2})?$')
    if not timepattern.fullmatch(formdata['time']):
        results.append({'name': 'time', 'status': 'must be formatted as [[hh:]mm:]ss[.dd]'})
        
    bibpattern = compile('^\d{2,8}$')
    if not bibpattern.fullmatch(formdata['bibno']):
        results.append({'name': 'bibno', 'status': 'must be a number between 2 and 8 digits'})
        
    return results

class ResultsView(TmConnectorView):
    ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
    ## not present in the data. Need to revisit this later.
    # def filterrowssince(self, since):
    #     if since:
    #         sincedt = sincerender.asc2dt(since).astimezone(utc)
    #         # self.queryfilters.append(Result.update_time >= sincedt)
    #         # print(f'getting updated since {sincedt}')

    # def getrowssince(self):
    #     rows = Result.query.filter_by(**self.queryparams).filter(*self.queryfilters).all()
    #     self._responsedata = []
    #     for row in rows:
    #         self._responsedata += self.dte.get_response_data(row)
    
    def editor_method_postcommit(self, form):
        # LOCK file access
        filelock.acquire()
        
        # # test lock
        # from time import sleep
        # current_app.logger.debug(f'sleeping')
        # sleep(10)
        # current_app.logger.debug(f'awake')

        # set place
        rows = Result.query.filter_by(**self.queryparams).filter(*self.queryfilters).order_by(Result.time, Result.tmpos, Result.tmpos).all()
        place = 1
        for row in rows:
            row.place = place
            place += 1
        db.session.commit()
        # note table is refreshed after the create (afterdatatables.js editor.on('postCreate'))
        # so place display is correct

        # get output file pathname
        filesetting = Setting.query.filter_by(name='output-file').one_or_none()
        if filesetting:
            filepath = join('/output_dir', filesetting.value)
            
            # create temporary file
            from tempfile import TemporaryDirectory
            fdir = TemporaryDirectory()
            tmpfname = join(fdir.name, filesetting.value)
            with open(tmpfname, mode='w') as f:
                csvf = DictWriter(f, fieldnames=filecolumns, extrasaction='ignore')
                for row in rows:
                    rowdict = {}
                    db2file.transform(row, rowdict)
                    csvf.writerow(rowdict)

            # overwrite file
            current_app.logger.debug(f'overwriting {filesetting.value}')
            copy(tmpfname, filepath)
            fdir.cleanup()

        ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
        ## not present in the data. Need to revisit this later.
        # if 'since' in form:
        #     since = form['since']
    
        #     # bring in all rows since the requested time
        #     self.filterrowssince(since)
        #     self.getrowssince()

        # UNLOCK file access
        filelock.release()
        
    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        # self.race set in self.permission()
        race_id = session['_results_raceid'] if '_results_raceid' in session else None
        self.race = Race.query.filter_by(id=race_id).one_or_none()
        self.queryparams['race_id'] = race_id
        
        ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
        ## not present in the data. Need to revisit this later.
        # self.queryfilters = []
        # since = request.args.get('since', None)
        # self.filterrowssince(since)

    def createrow(self, formdata):
        '''
        creates row in database

        :param formdata: data from create form
        :rtype: returned row for rendering, e.g., from DataTablesEditor.get_response_data()
        '''
        # make sure we record the row's race id
        formdata['race_id'] = self.race.id

        # return the row
        row = super().createrow(formdata)

        return row

results_view = ResultsView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=Result,
    template='results.jinja2',
    pagename='results',
    endpoint='public.results',
    rule='/results',
    pretablehtml=get_results_filters,
    dbmapping=results_dbmapping,
    formmapping=results_formmapping,
    validate=results_validate,
    idSrc='rowid',
    buttons=[
        'edit',
        'create',
        'remove',
        'csv'
    ],
    clientcolumns = [
        {'data': 'placepos', 'name': 'placepos', 'label': 'Place', 'type': 'readonly', 'fieldInfo': 'calculated by the system'},
        {'data': 'tmpos', 'name': 'tmpos', 'label': 'TM Pos', 'fieldInfo': 'received from time machine'},
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No', 'className': 'bibno_field'},
        {'data': 'time', 'name': 'time', 'label': 'Time', 'className': 'time_field'},
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

races_dbattrs = 'id,name,date'.split(',')
races_formfields = 'rowid,name,date'.split(',')
races_dbmapping = dict(zip(races_dbattrs, races_formfields))
races_formmapping = dict(zip(races_formfields, races_dbattrs))
races_dbmapping['date'] = lambda formrow: dtrender.asc2dt(formrow['date']).date()
races_formmapping['date'] = lambda dbrow: dtrender.dt2asc(dbrow.date)

def races_validate(action, formdata):
    races = []

    return races

class RacesView(TmConnectorView):
    pass

races_view = RacesView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=Race,
    template='datatables.jinja2',
    pagename='races',
    endpoint='public.races',
    rule='/races',
    dbmapping=races_dbmapping,
    formmapping=races_formmapping,
    validate=races_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'create',
        'edit',
        'remove',
    ],
    clientcolumns = [
        {'data': 'date', 'name': 'date', 'label': 'Date',
         'type': 'datetime',
         'className': 'field_req',
        },
        {'data': 'name', 'name': 'name', 'label': 'Name',
         'className': 'field_req',
         },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
        'order': [['date:name','desc']],
    },
)
races_view.register()

settings_dbattrs = 'id,name,value'.split(',')
settings_formfields = 'rowid,name,value'.split(',')
settings_dbmapping = dict(zip(settings_dbattrs, settings_formfields))
settings_formmapping = dict(zip(settings_formfields, settings_dbattrs))

def settings_validate(action, formdata):
    settings = []

    return settings

class settingsView(TmConnectorView):
    pass

settings_view = settingsView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=Setting,
    template='datatables.jinja2',
    pagename='settings',
    endpoint='public.settings',
    rule='/settings',
    dbmapping=settings_dbmapping,
    formmapping=settings_formmapping,
    validate=settings_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'create',
        'edit',
        'remove',
    ],
    clientcolumns = [
        {'data': 'name', 'name': 'name', 'label': 'Setting',
         'className': 'field_req',
        },
        {'data': 'value', 'name': 'value', 'label': 'Value',
         'className': 'field_req',
         },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
settings_view.register()

class SetParamsApi(MethodView):
    def post(self):
        try:
            form = request.form
            for key in form:
                session[f'_results_{key}'] = form[key]
            
            output_result = {'status' : 'success'}

            return jsonify(output_result)

        except Exception as e:
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)

params_api = SetParamsApi.as_view('_setparams')
bp.add_url_rule('/_setparams', view_func=params_api, methods=['POST',])

class PostResultApi(MethodView):
    def post(self):
        try:
            ## LOCK file access
            filelock.acquire()
            
            # # test lock
            # from time import sleep
            # current_app.logger.debug(f'sleeping')
            # sleep(10)
            # current_app.logger.debug(f'awake')

            # receive message
            msg = request.json
            current_app.logger.debug(f'received data {msg}')
            
            # get output file pathname
            filesetting = Setting.query.filter_by(name='output-file').one_or_none()
            if filesetting:
                filepath = join('/output_dir', filesetting.value)

            # handle messages from tm-reader-client
            opcode = msg.pop('opcode', None)
            if opcode in ['primary', 'select']:
                
                # determine place. if no records yet, create the output file
                lastrow = Result.query.filter_by(race_id=msg['raceid']).order_by(Result.place.desc()).first()
                if lastrow:
                    place = lastrow.place + 1
                else:
                    place = 1
                    # create file
                    if filesetting:
                        with open(filepath, mode='w') as f:
                            current_app.logger.info(f'creating {filesetting.value}')
                    
                # write to database
                result = Result()
                result.bibno = msg['bibno'] if 'bibno' in msg else None
                result.tmpos = msg['pos']
                result.time = timesecs(msg['time'])
                result.race_id = msg['raceid']
                result.place = place
                db.session.add(result)
                db.session.commit()
                
                # write to the file
                if filesetting:
                    with open(filepath, mode='a') as f:
                        filedata = {}
                        db2file.transform(result, filedata)
                        current_app.logger.debug(f'appending to {filesetting.value}: {filedata["pos"],filedata["bibno"],filedata["time"]}')
                        csvf = DictWriter(f, fieldnames=filecolumns, extrasaction='ignore')
                        csvf.writerow(filedata)
                
                
            # how did this happen?
            else:
                current_app.logger.error(f'unknown opcode received: {opcode}')

            ## UNLOCK file access and return
            filelock.release()
            return jsonify(status='success')

        except Exception as e:
            ## UNLOCK file access
            filelock.release()
            
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        

postresult_api = PostResultApi.as_view('_postresult')
bp.add_url_rule('/_postresult', view_func=postresult_api, methods=['POST',])
