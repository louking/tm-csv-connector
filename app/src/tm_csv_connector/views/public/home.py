'''
home - public views
=================================
'''
# standard
from datetime import timedelta
from traceback import format_exception_only, format_exc
from pytz import utc

# pypi
from flask import g, render_template, session, request, current_app, jsonify
from flask.views import MethodView
from loutilities.tables import DbCrudApi
from loutilities.timeu import asctime, timesecs
from dominate.tags import div, button, span, select, option, input_
from loutilities.filters import filtercontainerdiv

# homegrown
from . import bp
from ...model import db, Race, Result, Setting

class ParameterError(Exception): pass

dtrender = asctime('%Y-%m-%d')
sincerender = asctime('%Y-%m-%dT%H:%M:%S%z')

class TmConnectorView (DbCrudApi):
    def permission(self):
        self.race = Race.query.filter_by(id=session['_results_raceid']).one_or_none()
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
    results_filters = filtercontainerdiv()
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
    results_filter_outputdir = div(_class='filter-item')
    results_filters += results_filter_outputdir
    with results_filter_outputdir:
        span('Output Dir', _class='label')
        with span(_class='filter'):
            if '_results_outputdir' not in session:
                session['_results_outputdir'] = ''
            input_(id="outputdir", value=session['_results_outputdir'], type="text", name="outputdir", _class="validate", required='true', aria_required="true", onchange="setParams()")
    return results_filters.render()

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
        rows = Result.query.filter_by(**self.queryparams).filter(*self.queryfilters).order_by(Result.time, Result.tmpos, Result.tmpos).all()
        place = 1
        for row in rows:
            row.place = place
            place += 1
        db.session.commit()
        # note table is refreshed after the create (afterdatatables.js editor.on('postCreate'))
        # so place display is correct
        
        ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
        ## not present in the data. Need to revisit this later.
        # if 'since' in form:
        #     since = form['since']
    
        #     # bring in all rows since the requested time
        #     self.filterrowssince(since)
        #     self.getrowssince()

    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        # self.race set in self.permission()
        self.race = Race.query.filter_by(id=session['_results_raceid']).one_or_none()
        self.queryparams['race_id'] = self.race.id
        
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
        {'data': 'placepos', 'name': 'placepos', 'label': 'Place'},
        {'data': 'tmpos', 'name': 'tmpos', 'label': 'TM Pos'},
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No'},
        {'data': 'time', 'name': 'time', 'label': 'Time'},
        # for testing only
        # {'data': 'update_time', 'name': 'update_time', 'label': 'Update Time', 'type': 'readonly'},
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
    edoptions={
        'formOptions': {
            'inline': {
                # uses name field as key; value is used for editor.inline() options
                'bibno': {'submitOnBlur': True},
                'time': {'submitOnBlur': True},
            },
        }
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
