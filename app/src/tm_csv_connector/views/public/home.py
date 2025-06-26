'''
home - public views
=================================
'''
# standard
from datetime import timedelta
from csv import DictWriter
from os.path import join

# pypi
from flask import render_template, session, current_app, url_for
from flask.views import MethodView
from dominate.tags import div, button, span, select, option, p, i
from dominate.tags import table, thead, tbody, tr, th, td
from dominate.util import text
from sqlalchemy import update, and_, select as sqlselect
from loutilities.tables import DbCrudApi
from loutilities.tables import rest_url_for
from loutilities.timeu import asctime
from loutilities.filters import filtercontainerdiv, filterdiv, yadcfoption

# homegrown
from . import bp
from ...model import db, Race, Result, ScannedBib, BluetoothDevice, BluetoothType
from ...model import ChipRead, ChipBib, ChipReader, AppLog, Setting
from ...times import asc2time, time2asc
from ..common import ResultsView, get_results_posttablehtml, results_validate, results_dbmapping, results_formmapping
from ...fileformat import filecolumns, db2file, filelock, lock, unlock

# https://docs.python.org/3/library/datetime.html#datetime.tzinfo
from datetime import tzinfo
import time as _time

STDOFFSET = timedelta(seconds = -_time.timezone)
if _time.daylight:
    DSTOFFSET = timedelta(seconds = -_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

class LocalTimezone(tzinfo):

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        stamp = _time.mktime(tt)
        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

Local = LocalTimezone()

dtrender = asctime('%Y-%m-%d')
sincerender = asctime('%Y-%m-%dT%H:%M:%S%z')
logrender = asctime('%Y-%m-%d %H:%M:%S')

class TmConnectorView (DbCrudApi):
    def permission(self):
        session.permanent = True
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

def get_results_filters():
    prehtml = div()
    
    # NOTE: this will be overwritten from the browser window, though
    comports = ['COM3', 'COM4', 'COM5', 'COM6']
    
    if '_results_scannerport' in session and session['_results_scannerport'] not in comports:
        comports.append(session['_results_scannerport'])
    if '_results_port' in session and session['_results_port'] not in comports:
        comports.append(session['_results_port'])
    comports.sort()
    
    with prehtml.add(filtercontainerdiv()).add(table()):
        with thead().add(tr()):
            th('')
            th('Time Machine', style='text-align: center;')
            th('Scanner', style='text-align: center;')
            th('Chip Reader', style='text-align: center;')
        
        with tbody().add(tr()):
            with td().add(div(_class='filter-item')):
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
        
            with td().add(div(_class='filter-item')):
                # span('Port', _class='label')
                with span(_class='filter'):
                    with select(id='port', name="port", _class="validate", required='true', aria_required="true", onchange="setParams()"):
                        for port in comports:
                            if '_results_port' in session and port == session['_results_port']:
                                option(port, selected='true')
                            else:
                                option(port)
        
                div(button("placeholder", id="connect-disconnect", _class='filter-item ui-button'), _class='filter')
        
            with td().add(div(_class='filter-item')):
                # span('Port', _class='label')
                with span(_class='filter'):
                    with select(id='scannerport', name="scannerport", _class="validate", required='true', aria_required="true", onchange="setParams()"):
                        for port in comports:
                            if '_results_scannerport' in session and port == session['_results_scannerport']:
                                option(port, selected='true')
                            else:
                                option(port)
        
                div(button("placeholder", id="scanner-connect-disconnect", _class='filter-item ui-button'), _class='filter')
        
            with td().add(div(_class='filter-item')):
                # Chip Readers
                chipreaders = [c[0] for c in db.session.execute(sqlselect(ChipReader)).all()]
                chipreaders.sort(key=lambda c: c.reader_id)
                with table().add(tbody()):
                    for chipreader in chipreaders:
                        with tr():
                            td(chipreader.name)                
                            td(i(id=f'chipreader-alert-{chipreader.reader_id}', _class="fa-solid fa-circle", style="color: lightgrey;"))
                            td(button(
                                "placeholder", 
                                id=f"chipreader{chipreader.reader_id}-connect-disconnect", 
                                reader_id=chipreader.reader_id,
                                ipaddr=chipreader.ipaddr,
                                fport=chipreader.fport,
                                _class='filter-item ui-button'
                                ), 
                               _class='filter'
                            )
                            
        
    return prehtml.render()

class ResultsViewNormal(ResultsView, TmConnectorView):
    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        race_id = session['_results_raceid'] if '_results_raceid' in session else None
        self.race = Race.query.filter_by(id=race_id).one_or_none()
        self.queryparams['race_id'] = race_id
        # current_app.logger.debug(f'queryparams: {self.queryparams}')

    def set_queue_filters(self):
        """sets queue filters

        Returns:
            boolean: True if caller should update the queued scanned results
        """
        race_id = session['_results_raceid'] if '_results_raceid' in session else None
        race = Race.query.filter_by(id=race_id).one_or_none()
        if race:
            process_queue = True
            self.result_queue_filter = [Result.race_id == race_id]
            self.scannedbib_queue_filter = [ScannedBib.race_id == race_id]

        else:
            process_queue = False
            
        return process_queue

    def createrow(self, formdata):
        '''
        creates row in database

        :param formdata: data from create form
        :rtype: returned row for rendering, e.g., from DataTablesEditor.get_response_data()
        '''
        # make sure we record the row's race id
        formdata['race_id'] = self.race.id

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
                    Result.race_id == self.result.race_id,
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

results_view = ResultsViewNormal(
    app=bp,  # use blueprint instead of app
    db=db,
    model=Result,
    template='results.jinja2',
    pagename='results',
    endpoint='public.results',
    rule='/results',
    pretablehtml=get_results_filters,
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

races_dbattrs = 'id,name,date,start_time'.split(',')
races_formfields = 'rowid,name,date,start_time'.split(',')
races_dbmapping = dict(zip(races_dbattrs, races_formfields))
races_formmapping = dict(zip(races_formfields, races_dbattrs))
races_dbmapping['date'] = lambda formrow: dtrender.asc2dt(formrow['date']).date()
races_formmapping['date'] = lambda dbrow: dtrender.dt2asc(dbrow.date)
races_dbmapping['start_time'] = lambda formrow: asc2time(formrow['start_time'])
races_formmapping['start_time'] = lambda dbrow: time2asc(dbrow.start_time) if dbrow.start_time != None else None

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
        {'data': 'name', 'name': 'name', 'label': 'Name',
         'className': 'field_req',
         },
        {'data': 'date', 'name': 'date', 'label': 'Date',
         'type': 'datetime',
         'className': 'field_req',
        },
        {'data': 'start_time', 'name': 'start_time', 'label': 'Start Time',
         'type': 'datetime',
         'className': 'field_req',
         'ed': {
             'format': 'HH:mm:ss.SS',
         }
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

# NOTE: while this table *seems* like it can be updated, the values in the type column are hard
# coded in results.js. So if new values are added, results.js needs to be updated

bluetoothtypes_dbattrs = 'id,type,description'.split(',')
bluetoothtypes_formfields = 'rowid,type,description'.split(',')
bluetoothtypes_dbmapping = dict(zip(bluetoothtypes_dbattrs, bluetoothtypes_formfields))
bluetoothtypes_formmapping = dict(zip(bluetoothtypes_formfields, bluetoothtypes_dbattrs))

def bluetoothtypes_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        text('NOTE: updates to Type or new entries require a code change to results.js')
    return pretablehtml.render()

def bluetoothtypes_validate(action, formdata):
    bluetoothtypes = []

    return bluetoothtypes

class bluetoothtypesView(TmConnectorView):
    pass

bluetoothtypes_view = bluetoothtypesView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=BluetoothType,
    template='datatables.jinja2',
    pretablehtml=bluetoothtypes_filters(),
    pagename='Bluetooth Types',
    endpoint='public.bluetoothtypes',
    rule='/bluetoothtypes',
    dbmapping=bluetoothtypes_dbmapping,
    formmapping=bluetoothtypes_formmapping,
    validate=bluetoothtypes_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'create',
        'edit',
        'remove',
    ],
    clientcolumns = [
        {'data': 'type', 'name': 'type', 'label': 'Type',
         'className': 'field_req',
        },
        {'data': 'description', 'name': 'description', 'label': 'Description',
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
bluetoothtypes_view.register()


bluetoothdevices_dbattrs = 'id,name,type,hwaddr'.split(',')
bluetoothdevices_formfields = 'rowid,name,type,hwaddr'.split(',')
bluetoothdevices_dbmapping = dict(zip(bluetoothdevices_dbattrs, bluetoothdevices_formfields))
bluetoothdevices_formmapping = dict(zip(bluetoothdevices_formfields, bluetoothdevices_dbattrs))

def bluetoothdevices_validate(action, formdata):
    bluetoothdevices = []

    return bluetoothdevices

class BluetoothDevicesView(TmConnectorView):
    pass

bluetoothdevices_view = BluetoothDevicesView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=BluetoothDevice,
    template='datatables.jinja2',
    pagename='Bluetooth Devices',
    endpoint='public.bluetoothdevices',
    rule='/bluetoothdevices',
    dbmapping=bluetoothdevices_dbmapping,
    formmapping=bluetoothdevices_formmapping,
    validate=bluetoothdevices_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'create',
        'edit',
        'remove',
    ],
    clientcolumns = [
        {'data': 'name', 'name': 'name', 'label': 'Name',
         'className': 'field_req',
         },
        {'data': 'type', 'name': 'type', 'label': 'Type',
         'className': 'field_req',
         '_treatment': {
             'relationship': {'fieldmodel': BluetoothType, 'labelfield': 'type',
                             'formfield': 'type',
                             'dbfield': 'type',
                             'uselist': False,
                             }}
         },
        {'data': 'hwaddr', 'name': 'hwaddr', 'label': 'HW Addr',
         'className': 'field_req',
         'fieldInfo': 'determine using Device Manager > Properties > Details > Bluetooth device address',
        },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
bluetoothdevices_view.register()

chipreads_dbattrs = 'id,race.raceyear,reader_id,receiver_id,tag_id,bib,contig_ctr,display_date,time,rssi,types,source'.split(',')
chipreads_formfields = 'rowid,raceyear,reader_id,receiver_id,tag_id,bib,contig_ctr,display_date,time,rssi,types,source'.split(',')
chipreads_dbmapping = dict(zip(chipreads_dbattrs, chipreads_formfields))
chipreads_formmapping = dict(zip(chipreads_formfields, chipreads_dbattrs))

def chipreads_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
                  i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('chipreads-external-filter-raceyear', 'Race')
        filterdiv('chipreads-external-filter-display_date', 'Date')
        filterdiv('chipreads-external-filter-tag_id', 'Chips')
        filterdiv('chipreads-external-filter-bib', 'Bibs')
    return pretablehtml.render()

chipreads_yadcf_options = [
    yadcfoption('raceyear:name', 'chipreads-external-filter-raceyear', 'select', placeholder='Select races', width='300px', select_type='select2'),
    yadcfoption('display_date:name', 'chipreads-external-filter-display_date', 'date'),
    yadcfoption('tag_id:name', 'chipreads-external-filter-tag_id', 'multi_select', placeholder='Select', width='200px'),
    yadcfoption('bib:name', 'chipreads-external-filter-bib', 'multi_select', placeholder='Select', width='200px'),
]

# need set_yadcf_data param to tables class to pull possible filters
def chipreads_set_yadcf_data():
    getcol = lambda colname: [col.mData for col in chipreads_view.servercolumns].index(colname)

    # add filters for date, tag_id, bib
    yadcf_data = []
    
    # unfortunately the order_by clause is ignored by yadcf, which seems to sort alphabetically
    matches = [str(row[0]) for row in db.session.query(Race.raceyear).order_by(Race.date.desc()).all()]
    yadcf_data.append((f'yadcf_data_{getcol('raceyear')}', matches))

    matches = [str(row[0]) for row in db.session.query(ChipRead.date).distinct().all()]
    yadcf_data.append((f'yadcf_data_{getcol('display_date')}', matches))
    
    matches = [row[0] for row in db.session.query(ChipRead.tag_id).distinct().all()]
    yadcf_data.append((f'yadcf_data_{getcol('tag_id')}', matches))
    
    matches = [row[0] for row in db.session.query(ChipRead.bib).distinct().all()]
    yadcf_data.append((f'yadcf_data_{getcol('bib')}', matches))

    return yadcf_data

class ChipreadsView(TmConnectorView):
    pass

chipreads_view = ChipreadsView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=ChipRead,
    template='chipreads.jinja2',
    pretablehtml=chipreads_filters(),
    yadcfoptions=chipreads_yadcf_options,
    set_yadcf_data=chipreads_set_yadcf_data,
    pagename='Chip Reads',
    endpoint='public.chipreads',
    rule='/chipreads',
    dbmapping=chipreads_dbmapping,
    formmapping=chipreads_formmapping,
    serverside=True,
    idSrc='rowid',
    buttons=lambda: [
        {
            'extend': 'create',
            'text': 'Import',
            'name': 'import-chip-log',
            'editor': {'eval': 'chipreads_import_saeditor.saeditor'},
            'url': url_for('public._chipreads'),
            'action': {
                'eval': 'chipreads_import("{}")'.format(rest_url_for('public._chipreads'))
            }
        },
        'csv'
    ],
    clientcolumns = [
        {'data': 'raceyear', 'name': 'raceyear', 'label': 'race',
         'type': 'readonly',
         },
        {'data': 'reader_id', 'name': 'reader_id', 'label': 'Reader ID',
         'type': 'readonly',
         },
        {'data': 'receiver_id', 'name': 'receiver_id', 'label': 'Receiver ID',
         'type': 'readonly',
         },
        {'data': 'tag_id', 'name': 'tag_id', 'label': 'Chip',
         'type': 'readonly',
         '_ColumnDT_args' :
             {'sqla_expr': ChipRead.tag_id, 'search_method': 'yadcf_multi_select'},
         },
        {'data': 'bib', 'name': 'bib', 'label': 'Bib',
         'type': 'readonly',
         '_ColumnDT_args' :
             {'sqla_expr': ChipRead.bib, 'search_method': 'yadcf_multi_select'},
         },
        {'data': 'contig_ctr', 'name': 'contig_ctr', 'label': 'Counter',
         'type': 'readonly',
         },
        {'data': 'display_date', 'name': 'display_date', 'label': 'Date',
         'type': 'readonly',
        #  '_ColumnDT_args' :
        #      {'sqla_expr': ChipRead.display_date, 'search_method': 'yadcf_range_date'},
        },
        {'data': 'time', 'name': 'time', 'label': 'Time',
         'type': 'readonly',
         'render': {'eval': 'render_secs2time'},
        },
        {'data': 'rssi', 'name': 'rssi', 'label': 'RSSI',
         'type': 'readonly',
        },
        {'data': 'types', 'name': 'types', 'label': 'Types',
         'type': 'readonly',
        },
        {'data': 'source', 'name': 'source', 'label': 'Source',
         'type': 'readonly',
        },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
        'lengthMenu': [ [10, 25, 50, 100, 500, -1], [10, 25, 50, 100, 500, 'All'] ],
        'order': [['display_date:name','desc'],['time:name','desc']],
    },
)
chipreads_view.register()

chip2bib_dbattrs = 'id,race.raceyear,tag_id,bib'.split(',')
chip2bib_formfields = 'rowid,raceyear,tag_id,bib'.split(',')
chip2bib_dbmapping = dict(zip(chip2bib_dbattrs, chip2bib_formfields))
chip2bib_formmapping = dict(zip(chip2bib_formfields, chip2bib_dbattrs))

def get_chip2bib_filters():
    pretablehtml = filtercontainerdiv()
    with pretablehtml:
        with span(id='spinner', style='display:none;'):
                  i(cls='fa-solid fa-spinner fa-spin')
        filterdiv('chip2bib-external-filter-raceyear', 'Race')
    return pretablehtml.render()

chip2bib_yadcf_options = [
    yadcfoption('raceyear:name', 'chip2bib-external-filter-raceyear', 'select', placeholder='Select races', width='300px', select_type='select2'),
]

# need set_yadcf_data param to tables class to pull possible filters
def chip2bib_set_yadcf_data():
    getcol = lambda colname: [col.mData for col in chip2bib_view.servercolumns].index(colname)

    # add filters for date, tag_id, bib
    yadcf_data = []
    
    # unfortunately the order_by clause is ignored by yadcf, which seems to sort alphabetically
    matches = [str(row[0]) for row in db.session.query(Race.raceyear).order_by(Race.date.desc()).all()]
    yadcf_data.append((f'yadcf_data_{getcol('raceyear')}', matches))

    return yadcf_data

class ChipBibView(TmConnectorView):
    pass

chip2bib_view = ChipBibView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=ChipBib,
    template='chip2bib.jinja2',
    pretablehtml=get_chip2bib_filters,
    yadcfoptions = chip2bib_yadcf_options,
    set_yadcf_data = chip2bib_set_yadcf_data,
    pagename='Chip/Bib Map',
    endpoint='public.chip2bib',
    rule='/chip2bib',
    dbmapping=chip2bib_dbmapping,
    formmapping=chip2bib_formmapping,
    serverside=True,
    idSrc='rowid',
    buttons=lambda: [
        {
            'extend': 'create',
            'text': 'Import',
            'name': 'import-chip-log',
            'editor': {'eval': 'chip2bib_import_saeditor.saeditor'},
            'url': url_for('public._chip2bib'),
            'action': {
                'eval': 'chip2bib_import("{}")'.format(rest_url_for('public._chip2bib'))
            }
        },
        'csv'
    ],
    clientcolumns = [
        {'data': 'raceyear', 'name': 'raceyear', 'label': 'race',
         'type': 'readonly',
         },
        {'data': 'tag_id', 'name': 'tag_id', 'label': 'chip',
         'type': 'readonly',
         },
        {'data': 'bib', 'name': 'bib', 'label': 'bib',
         'type': 'readonly',
         },
    ],
    dtoptions={
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
        'lengthMenu': [ [10, 25, 50, 100, -1], [10, 25, 50, 100, 'All'] ],
    },
)
chip2bib_view.register()

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


chipreaders_dbattrs = 'id,name,reader_id,ipaddr,fport'.split(',')
chipreaders_formfields = 'rowid,name,reader_id,ipaddr,fport'.split(',')
chipreaders_dbmapping = dict(zip(chipreaders_dbattrs, chipreaders_formfields))
chipreaders_formmapping = dict(zip(chipreaders_formfields, chipreaders_dbattrs))

def chipreaders_validate(action, formdata):
    chipreaders = []

    return chipreaders

chipreaders_view = TmConnectorView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=ChipReader,
    template='datatables.jinja2',
    pagename='Chip Readers',
    endpoint='public.chipreaders',
    rule='/chipreaders',
    dbmapping=chipreaders_dbmapping,
    formmapping=chipreaders_formmapping,
    validate=chipreaders_validate,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[
        'create',
        'edit',
        'remove',
    ],
    clientcolumns = [
        {'data': 'name', 'name': 'name', 'label': 'Name',
         'className': 'field_req',
        },
        {'data': 'reader_id', 'name': 'reader_id', 'label': 'Reader ID',
         'className': 'field_req',
         },
        {'data': 'ipaddr', 'name': 'ipaddr', 'label': 'IP Addr',
         'className': 'field_req',
         },
        {'data': 'fport', 'name': 'fport', 'label': 'Filtered Port',
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
chipreaders_view.register()


applog_dbattrs = 'id,time,info'.split(',')
applog_formfields = 'rowid,time,info'.split(',')
applog_dbmapping = dict(zip(applog_dbattrs, applog_formfields))
applog_formmapping = dict(zip(applog_formfields, applog_dbattrs))
applog_formmapping['time'] = lambda dbrow: logrender.dt2asc(dbrow.time + Local.utcoffset(dbrow.time))

applog_view = TmConnectorView(
    app=bp,  # use blueprint instead of app
    db=db,
    model=AppLog,
    template='datatables.jinja2',
    pagename='App Log',
    endpoint='public.applog',
    rule='/applog',
    dbmapping=applog_dbmapping,
    formmapping=applog_formmapping,
    servercolumns=None,  # not server side
    idSrc='rowid',
    buttons=[],
    clientcolumns = [
        {'data': 'time', 'name': 'time', 'label': 'Time',
         },
        {'data': 'info', 'name': 'info', 'label': 'Log Info',
         },
    ],
    dtoptions={
        'order': [['time:name', 'desc']],
        'scrollCollapse': True,
        'scrollX': True,
        'scrollXInner': "100%",
        'scrollY': True,
    },
)
applog_view.register()

