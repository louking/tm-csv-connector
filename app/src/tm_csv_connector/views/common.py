'''tm_csv_connector.views.common
=================================
This module contains common view classes and methods for the TM CSV Connector application.
'''

# standard
from copy import copy

# pypi
from dominate.tags import div, button, span, p
from dominate.util import text
from sqlalchemy import select as sqlselect

# homegrown
from ..model import db, Result
from ..fileformat import filelock, refreshfile, lock, unlock
from ..times import asc2time, time2asc

class ParameterError(Exception): pass

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

def get_results_posttablehtml():
    updates_suspended_warning = div()
    with updates_suspended_warning:
        p('display updates suspended - deselect to resume', id='updates-suspended', style='color: white; font-weight: bold; background-color: red; text-align: center; display: none;')
    return updates_suspended_warning.render()

def results_validate(action, formdata):
    results = []
    from re import compile
    
    timepattern = compile(r'^(\d{1,2}:)?([0-5]\d:)?[0-5]\d(\.\d{0,2})?$')
    if not timepattern.fullmatch(formdata['time']):
        results.append({'name': 'time', 'status': 'must be formatted as [[hh:]mm:]ss[.dd]'})
        
    bibpattern = compile(r'^\d{1,5}$')
    if not bibpattern.fullmatch(formdata['bibno']):
        results.append({'name': 'bibno', 'status': 'must be a number between 1 and 5 digits'})
        
    return results


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


class ResultsView():
    
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
                
    def nexttablerow(self):
        """add result_confirmed class to row if is_confirmed

        Returns:
            dict: row dict
        """
        row = super().nexttablerow()
        
        if row['is_confirmed']:
            row['DT_RowClass'] = 'confirmed'

        return row
    
    def deleterow(self, thisid):
        # don't allow delete if this result has a scanned bib assigned
        thisresult = Result.query.filter_by(id=thisid).one()
        if thisresult.scannedbib:
            self._error='cannot delete result which has scanned bib assigned - use Ins first'
            raise ParameterError('cannot delete result which has scanned bib assigned - use Ins first')
            
        # if edit for previously confirmed entry is done, this will cause the file to be rewritten
        self.check_confirmed(thisid)
        return super().deleterow(thisid)
    
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
        # need flush here else Result query below will not return updated rows
        db.session.flush()

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


