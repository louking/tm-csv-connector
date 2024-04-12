'''
home - public views
=================================
'''
# standard
from datetime import timedelta
from os.path import join
from csv import DictWriter
from copy import copy

# pypi
from flask import render_template, session, current_app
from flask.views import MethodView
from loutilities.tables import DbCrudApi
from loutilities.timeu import asctime, timesecs
from dominate.tags import div, button, span, select, option, p
from dominate.tags import table, thead, tbody, tr, th, td
from dominate.util import text
from loutilities.filters import filtercontainerdiv
from sqlalchemy import update, and_, select as sqlselect

# homegrown
from . import bp
from ...model import db, Race, Result, Setting
from ...fileformat import filecolumns, db2file, filelock, refreshfile, lock, unlock

class ParameterError(Exception): pass

dtrender = asctime('%Y-%m-%d')
sincerender = asctime('%Y-%m-%dT%H:%M:%S%z')

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

def asc2time(asctime):
    # print(f'asctime={asctime}, timesecs(asctime)={timesecs(asctime)}')
    return timesecs(asctime)

def time2asc(dbtime):
    timestr = str(timedelta(seconds=dbtime))
    wholefrac = timestr.split('.')
    if len(wholefrac) == 1:
        wholefrac.append('0')
    whole, frac = wholefrac
    frac = f'{round(int(frac)/10000):02}'
    return '.'.join([whole, frac])

def scanned_bibno(dbrow):
    bibno = dbrow.scannedbib.bibno if dbrow.scannedbib else ''
    scanid = dbrow.scannedbib.id if dbrow.scannedbib else 'null'
    
    # if scannedbib has been received for this row, show the scanned bib number and buttons
    render = None
    if dbrow.had_scannedbib:
        scannedbib = span(_class="scannedbib", __pretty=False)
        use_state = 'ui-state-disabled' if bibno == dbrow.bibno or bibno == '0000' or not bibno or dbrow.is_confirmed else ''
        ins_state = 'ui-state-disabled' if dbrow.is_confirmed else ''
        del_state = 'ui-state-disabled' if dbrow.is_confirmed else ''
        with scannedbib:
            with span(style="margin-left: 2px;"):
                # actions processed in api.ScanActionApi.post()
                button('Use', type='button', _class=f"ui-button ui-corner-all ui-widget {use_state}", 
                        onclick=f'scan_action(event, {{action: "use", resultid: {dbrow.id}, scanid: {scanid}}})')
                button('Ins', type='button', _class=f"ui-button ui-corner-all ui-widget {ins_state}", 
                        onclick=f'scan_action(event, {{action: "insert", resultid: {dbrow.id}, scanid: {scanid}}})')
                button('Del', type='button', _class=f"ui-button ui-corner-all ui-widget {del_state}", 
                        onclick=f'scan_action(event, {{action: "delete", resultid: {dbrow.id}, scanid: {scanid}}})')
                text(f'{bibno}')
    
        render = scannedbib.render()
    
    return render

# using bibno in dbattrs for bibalert as this gets replaced in formmapping, and this is readonly
results_dbattrs = 'id,is_confirmed,tmpos,place,bibno,scannedbib.bibno,bibno,time,race_id,is_confirmed,update_time'.split(',')
results_formfields = 'rowid,is_confirmed,tmpos,placepos,bibalert,scanned_bibno,bibno,time,race_id,is_confirmed,update_time'.split(',')
results_dbmapping = dict(zip(results_dbattrs, results_formfields))
results_formmapping = dict(zip(results_formfields, results_dbattrs))
results_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
results_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)
results_formmapping['scanned_bibno'] = scanned_bibno
results_formmapping['is_confirmed'] = lambda dbrow: '<i class="fa-solid fa-file-circle-check"></i>' \
    if dbrow.is_confirmed else ''
results_formmapping['bibalert'] = lambda dbrow: '<i class="fa-solid fa-not-equal checkscanned"></i>' \
    if dbrow.scannedbib and dbrow.scannedbib.bibno != dbrow.bibno and dbrow.scannedbib.bibno != '0000' else ''

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
        
    return prehtml.render()

def get_results_posttablehtml():
    updates_suspended_warning = div()
    with updates_suspended_warning:
        p('display updates suspended - deselect to resume', id='updates-suspended', style='color: white; font-weight: bold; background-color: red; text-align: center; display: none;')
    return updates_suspended_warning.render()

def results_validate(action, formdata):
    results = []
    from re import compile
    
    timepattern = compile('^(\d{1,2}:)?([0-5]\d:)?[0-5]\d(\.\d{0,2})?$')
    if not timepattern.fullmatch(formdata['time']):
        results.append({'name': 'time', 'status': 'must be formatted as [[hh:]mm:]ss[.dd]'})
        
    bibpattern = compile('^\d{2,5}$')
    if not bibpattern.fullmatch(formdata['bibno']):
        results.append({'name': 'bibno', 'status': 'must be a number between 2 and 5 digits'})
        
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
    
    def check_confirmed(self, thisid):
        # flag for editor_method_postcommit; only rewrite file if a previously
        # confirmed entry was edited
        self.rewritefile = False
        
        if self.action != 'create':
            # retrieve the indicated row before any editing
            self.result = db.session.execute(
                sqlselect(Result)
                .where(Result.id == thisid)
            ).one()[0]

            # if the operator edited a previously confirmed entry, the file needs to be rewritten
            # the rewrite happens in editor_method_postcommit()
            if self.result.is_confirmed:
                self.rewritefile = True
                
    def beforequery(self):
        '''
        filter on current race
        :return:
        '''
        race_id = session['_results_raceid'] if '_results_raceid' in session else None
        self.race = Race.query.filter_by(id=race_id).one_or_none()
        self.queryparams['race_id'] = race_id
        
        ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
        ## not present in the data. Need to revisit this later.
        # self.queryfilters = []
        # since = request.args.get('since', None)
        # self.filterrowssince(since)

    def nexttablerow(self):
        """add result_confirmed class to row if is_confirmed

        Returns:
            dict: row dict
        """
        row = super().nexttablerow()
        
        if row['is_confirmed']:
            row['DT_RowClass'] = 'confirmed'

        return row
    
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
        
    def deleterow(self, thisid):
        # don't allow delete if this result has a scanned bib assigned
        thisresult = Result.query.filter_by(id=thisid).one()
        if thisresult.scannedbib:
            self._error='cannot delete result which has scanned bib assigned - use Ins first'
            raise ParameterError('cannot delete result which has scanned bib assigned - use Ins first')
            
        # if edit for previously confirmed entry is done, this will cause the file to be rewritten
        self.check_confirmed(thisid)
        return super().deleterow(thisid)
    
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
    
    def editor_method_postcommit(self, form):
        # LOCK file access
        lock(filelock)
        
        # # test lock
        # from time import sleep
        # current_app.logger.debug(f'sleeping')
        # sleep(10)
        # current_app.logger.debug(f'awake')

        # set place
        rows = Result.query.filter_by(**self.queryparams).filter(*self.queryfilters).order_by(Result.time, Result.tmpos).all()
        place = 1
        for row in rows:
            row.place = place
            place += 1

        # set had_scannedbib depending on whether the next result had a scanned bib
        if self.action == 'create':
            thisresult = Result.query.filter_by(id=self.created_id).one()
            filters = copy(self.queryfilters)
            filters.append(Result.place>thisresult.place)
            next_result = Result.query.filter_by(**self.queryparams).filter(*filters).order_by(Result.place).first()
            thisresult.had_scannedbib = next_result and next_result.had_scannedbib
        
        # commit again
        db.session.commit()
        # note table is refreshed after the create (afterdatatables.js editor.on('postCreate'))
        # so place display is correct

        # only rewrite the file if a previously confirmed row has been updated. see self.check_confirmed()
        if self.rewritefile:
            refreshfile(rows)
        
        ## commented out logic was for #9 but the refresh_table_data in afterdatatables.js was removing rows 
        ## not present in the data. Need to revisit this later.
        # if 'since' in form:
        #     since = form['since']
    
        #     # bring in all rows since the requested time
        #     self.filterrowssince(since)
        #     self.getrowssince()

        # UNLOCK file access
        unlock(filelock)

        
results_view = ResultsView(
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

