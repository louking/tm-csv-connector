'''
home - public views
=================================
'''
# standard
from datetime import timedelta

# pypi
from flask import g, render_template, jsonify
from flask.views import MethodView
from loutilities.tables import DbCrudApi
from loutilities.timeu import asctime, timesecs
from dominate.tags import div, button, span, select, option, input_
from loutilities.filters import filtercontainerdiv

# homegrown
from . import bp
from ...model import db, Race, Result, Setting

dtrender = asctime('%Y-%m-%d')

class TmConnectorView (DbCrudApi):
    def permission(self):
        self.race = Race.query.filter_by(id=g.interest).one_or_none()
        return True

class Home(MethodView):

    def get(self):
        return render_template('home.jinja2',
                               pagename='Home',
                               # causes redirect to current interest if bare url used
                               url_rule='/<interest>',
                               )

home_view = Home.as_view('home')
bp.add_url_rule('/', view_func=home_view, methods=['GET',])
bp.add_url_rule('/<interest>', view_func=home_view, methods=['GET',])

    
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

results_dbattrs = 'id,tmpos,place,bibno,time,race_id'.split(',')
results_formfields = 'rowid,tmpos,place,bibno,time,race_id'.split(',')
results_dbmapping = dict(zip(results_dbattrs, results_formfields))
results_formmapping = dict(zip(results_formfields, results_dbattrs))
results_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
results_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)

results_filters = filtercontainerdiv()
results_filters += div(button("placeholder", id="connect-disconnect", _class='filter-item'), _class='filter')
results_filter_port = div(_class='filter-item')
with results_filter_port:
    span('Port *', _class='label')
    with span(_class='filter'):
         with select(id='port', name="port", _class="validate", required='true', aria_required="true", onchange="setParams()"):
             option('COM3')
             option('COM4')
             option('COM8')
results_filters += results_filter_port
results_filter_outputdir = div(_class='filter-item')
with results_filter_outputdir:
    span('Output Dir *', _class='label')
    with span(_class='filter'):
        input_(id="outputdir", type="text", name="outputdir", _class="validate", required='true', aria_required="true", onchange="setParams()")
results_filters += results_filter_outputdir

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
    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        # self.race set in self.permission()
        self.race = Race.query.filter_by(id=g.interest).one_or_none()
        self.queryparams['race_id'] = self.race.id

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
    rule='/<interest>/results',
    endpointvalues={'interest': '<interest>'},
    pretablehtml=results_filters.render(),
    dbmapping=results_dbmapping,
    formmapping=results_formmapping,
    validate=results_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'edit',
        'create',
        'remove',
        'csv'
    ],
    clientcolumns = [
        {'data': 'place', 'name': 'place', 'label': 'Place'},
        {'data': 'tmpos', 'name': 'tmpos', 'label': 'TM Pos'},
        {'data': 'bibno', 'name': 'bibno', 'label': 'Bib No'},
        {'data': 'time', 'name': 'time', 'label': 'Time'},
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
