'''tm_csv_connector.views.common
=================================
This module contains common view classes and methods for the TM CSV Connector application.
'''

# standard
from copy import copy
from traceback import format_exception_only, format_exc
from os.path import join

# pypi
from flask import current_app, jsonify, request
from flask.views import MethodView
from dominate.tags import div, button, span, p
from dominate.util import text
from sqlalchemy import select as sqlselect

# homegrown
from ..model import db, Result, ScannedBib, Setting
from ..fileformat import filelock, refreshfile, lock, unlock
from ..times import asc2time, time2asc

class ParameterError(Exception): pass

BLANK_BIBNO = '0000' # blank bibno, used to indicate no bibno was scanned

def scanned_bibno(dbrow):
    bibno = dbrow.scannedbib.bibno if dbrow.scannedbib else ''
    scanid = dbrow.scannedbib.id if dbrow.scannedbib else 'null'
    
    # if scannedbib has been received for this row, show the scanned bib number and buttons
    render = None
    if dbrow.had_scannedbib:
        scannedbib = span(_class="scannedbib", __pretty=False)
        use_state = 'ui-state-disabled' if bibno == dbrow.bibno or bibno == BLANK_BIBNO or not bibno or dbrow.is_confirmed else ''
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
        
    # bibpattern = compile(r'^\d{1,5}$')
    # if not bibpattern.fullmatch(formdata['bibno']):
    #     results.append({'name': 'bibno', 'status': 'must be a number between 1 and 5 digits'})
        
    return results


# using bibno in dbattrs for bibalert as this gets replaced in formmapping, and this is readonly
results_dbattrs = 'id,is_confirmed,race_id,simulationrun_id,tmpos,place,bibno,scannedbib.bibno,bibno,time,is_confirmed,update_time'.split(',')
results_formfields = 'rowid,is_confirmed,race_id,simulationrun_id,tmpos,placepos,bibalert,scanned_bibno,bibno,time,is_confirmed,update_time'.split(',')
results_dbmapping = dict(zip(results_dbattrs, results_formfields))
results_formmapping = dict(zip(results_formfields, results_dbattrs))
results_dbmapping['time'] = lambda formrow: asc2time(formrow['time'])
results_formmapping['time'] = lambda dbrow: time2asc(dbrow.time)
results_formmapping['scanned_bibno'] = scanned_bibno
results_formmapping['is_confirmed'] = lambda dbrow: '<i class="fa-solid fa-file-circle-check"></i>' \
    if dbrow.is_confirmed else ''
results_formmapping['bibalert'] = lambda dbrow: '<i class="fa-solid fa-not-equal checkscanned"></i>' \
    if dbrow.scannedbib and dbrow.scannedbib.bibno != dbrow.bibno and dbrow.scannedbib.bibno != BLANK_BIBNO else ''


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
                
    def open(self):
        '''
        retrieve all the data in the indicated table
        
        adapted from loutilities.tables.DbCrudApi.open()
        
        NOTE: assumes not server table
        '''
        # not server table, rows will be handled in nexttablerow()
        # added order_by(Result.place) to ensure the results are in place order
        query = self.model.query.filter_by(**self.queryparams).filter(*self.queryfilters).order_by(Result.place)
        self.rows = iter(query.all())

    def get(self):
        # manage scanned bib queue before get
        # this can happen if a scanned bib and results are processed in parallel, apparently, 
        # because the database transactions may be concurrent
        process_queue = self.set_queue_filters()
        
        # only process queue if in valid queue context
        if process_queue:
            # lock "file" to mutex with scan and timemachine api
            lock(filelock)
        
            try:
                # get the results which don't have a scanned bib
                results = (Result.query.filter(
                    Result.had_scannedbib == False, *self.result_queue_filter)
                           .populate_existing().with_for_update()
                           .order_by(Result.place).all())
                resultsi = iter(results)
                # current_app.logger.debug(f'{self.__class__.__name__}.get(): {len(results)} results without scanned bib')
                
                lastresult = (Result.query.filter(Result.scannedbib_id.isnot(None), *self.result_queue_filter)
                              .populate_existing().with_for_update()
                              .order_by(Result.place.desc()).first())

                if lastresult:
                    last_scannedbib = lastresult.scannedbib
                    filters = [ScannedBib.order > last_scannedbib.order] + self.scannedbib_queue_filter
                else:
                    last_scannedbib = None
                    filters = self.scannedbib_queue_filter
                    
                # get the remaining scanned bibs
                scannedbibs = (ScannedBib.query.filter(*filters)
                               .populate_existing().with_for_update()
                               .order_by(ScannedBib.order).all())
                scannedbibsi = iter(scannedbibs)
                # current_app.logger.debug(f'{self.__class__.__name__}.get(): {len(scannedbibs)} scannedbibs after last_scannedbib {last_scannedbib}')
                
                try:
                    # loop, adding scannedbibs to results
                    while True:
                        scannedbib = next(scannedbibsi)
                        result = next(resultsi)
                        
                        result.scannedbib = scannedbib
                        result.had_scannedbib = True
                
                except StopIteration:
                    pass
                    
                db.session.commit()
                unlock(filelock)
                
            except:
                unlock(filelock)
                raise
        
        return super().get()

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
        thisresult = (Result.query.filter_by(id=thisid)
                      .populate_existing().with_for_update()
                      .one())
        if thisresult.scannedbib:
            self._error='cannot delete result which has scanned bib assigned - use Ins first'
            raise ParameterError('cannot delete result which has scanned bib assigned - use Ins first')
            
        # if edit for previously confirmed entry is done, this will cause the file to be rewritten
        self.check_confirmed(thisid)
        return super().deleterow(thisid)
    
    def editor_method_postcommit(self, form):
        # LOCK file access
        lock(filelock)
        
        try:
            # # test lock
            # from time import sleep
            # current_app.logger.debug(f'sleeping')
            # sleep(10)
            # current_app.logger.debug(f'awake')

            # set place
            rows = (Result.query.filter_by(**self.queryparams).filter(*self.queryfilters)
                    .populate_existing().with_for_update()
                    .order_by(Result.time, Result.tmpos).all())
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
                current_app.logger.debug(f'thisresult.place={thisresult.place}')
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
            
        except:
            db.session.rollback()
            # UNLOCK file access
            unlock(filelock)
            raise


class PostResultApi(MethodView):
    """must be overridden to
    send a result from tm-reader-client
    """
    def set_query(self):
        """initializes query parameters to retrieve Result records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        """
        raise NotImplementedError
    
    def new_result(self):
        """must be overridden to
        format a Result record

        Returns:
            Result()
        """
        raise NotImplementedError

    def post(self):
        try:
            ## LOCK file access
            current_app.logger.debug(f'{self.__class__.__name__}: requesting lock(filelock)')
            lock(filelock)
            current_app.logger.debug(f'{self.__class__.__name__}: lock(filelock) granted')
            
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
                lastrow = (Result.query.filter(*self.set_query())
                           .populate_existing().with_for_update()
                           .order_by(Result.place.desc()).first())
                if lastrow:
                    place = lastrow.place + 1
                else:
                    place = 1
                    # create file
                    if filesetting:
                        with open(filepath, mode='w') as f:
                            current_app.logger.info(f'creating {filesetting.value}')
                    
                # write to database
                result = self.new_result()
                result.bibno = msg['bibno'] if 'bibno' in msg else None
                result.tmpos = msg['pos']
                result.place = place
                result.is_confirmed = False
                
                current_app.logger.debug(f'{self.__class__.__name__}: add(result)')
                db.session.add(result)
            
            # how did this happen?
            else:
                current_app.logger.error(f'unknown opcode received: {opcode}')

            db.session.commit()
                
            ## UNLOCK file access and return
            current_app.logger.debug(f'{self.__class__.__name__}: unlock(filelock)')
            unlock(filelock)
            return jsonify(status='success')

        except Exception as e:
            ## UNLOCK file access
            current_app.logger.debug(f'{self.__class__.__name__}: unlock(filelock) [exception]')
            unlock(filelock)
            
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)

class PostBibApi(MethodView):
    """simulate a scanned bibno from barcode-scanner-client
    """
    def set_query(self):
        """must be overridden to
        initialize query parameters to retrieve ScannedBib records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        Raises:
            NotImplementedError: if not implemented by inheriting class
        """
        raise NotImplementedError
    
    def new_scannedbib(self):
        """must be overridden to
        format a ScannedBib record

        Returns:
            ScannedBib()
            
        Raises:
            NotImplementedError: if not implemented by inheriting class
        """
        raise NotImplementedError
    
    def post(self):

        try:
            ## LOCK file access
            current_app.logger.debug(f'{self.__class__.__name__}: requesting lock(filelock)')
            lock(filelock)
            current_app.logger.debug(f'{self.__class__.__name__}: lock(filelock) granted')

            # receive message
            msg = request.json
            current_app.logger.debug(f'received data {msg}')
            
            # handle messages from barcode-scanner-client
            opcode = msg.pop('opcode', None)
            if opcode in ['scannedbib']:
                # determine place. if no records yet, create the output file
                lastrow = (ScannedBib.query.filter(*self.set_query())
                           .populate_existing().with_for_update()
                           .order_by(ScannedBib.order.desc()).first())
                if lastrow:
                    order = lastrow.order + 1
                else:
                    order = 1
                    
                # write to database
                bibno = msg['bibno']
                # remove leading 0's if not 0000 ('0000' is "blank" bibno BLANK_BIBNO)
                if bibno != BLANK_BIBNO:
                    bibno = bibno.lstrip('0')

                scannedbib = self.new_scannedbib()
                scannedbib.bibno = bibno
                scannedbib.order = order
                
                db.session.add(scannedbib)
                db.session.flush()
                
            # how did this happen?
            else:
                current_app.logger.error(f'unknown opcode received: {opcode}')

            db.session.commit()
            current_app.logger.debug(f'{self.__class__.__name__}: committed')
                

            ## UNLOCK file access and return
            current_app.logger.debug(f'{self.__class__.__name__}: unlock(filelock)')
            unlock(filelock)
            return jsonify(status='success')

        except Exception as e:
            ## UNLOCK file access
            # current_app.logger.debug(f'{self.__class__.__name__}: unlock(filelock) [exception]')
            unlock(filelock)
            
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)

class ScanActionApi(MethodView):
    def get_source(self, result):
        """must be overridden to
        initialize source item to use for filtering
        
        Arts:
            result (object): result item to use for filtering
            
        Returns:
            source item, suitable for .filter(source==source)

        Raises:
            NotImplementedError: if not implemented by inheriting class
        """
        raise NotImplementedError
    
    def get_source_dict(self, source):
        """must be overridden to
        initialize source dictionary
        
        Args:
            source (object): source item to use for filtering
            
        Returns:
            {source dict}, suitable for .filter_by(**self.get_source_dict()) or 

        """
        raise NotImplementedError
    
    
    """update scan queue based on user action
    """
    def post(self):
        try:
            # options from home.scanned_bibno()
            options = request.form
            action = options['action']
            resultid = options['resultid']
            scanid = options['scanid']
            current_app.logger.debug(f'_scanaction: action={action} resultid={resultid} scanid={scanid}')
            
            # LOCK file access / place change / etc
            lock(filelock)
            
            # get the relevant records
            thisresult = Result.query.filter_by(id=resultid).one_or_none()
            thisscannedbib = ScannedBib.query.filter_by(id=scanid).one_or_none()
            
            # do some error checking
            error = []
            if not thisresult:
                error.append(f'Invalid resultid: {resultid}')
            if not thisscannedbib and action in ['use']:
                error.append(f'Invalid scanid: {scanid}')
            
            if not error:
                # show success
                output_result = {'status' : 'success'}

                # save source and place for insert, delete
                thissource = self.get_source(thisresult)
                thisplace = thisresult.place

                # TODO: is there any way to log this action so it can be imported into a simulation, i.e., without scan or result id?

                # handle cases 
                match action:
                    # use the scanned bibno as bibno
                    case 'use':
                        thisresult.bibno = thisscannedbib.bibno
                    
                    # insert blank scanned bibno before current result
                    # shift scanned bibnos to later results
                    case 'insert':
                        # need strictly greater than thisplace to get the later results
                        later_results = (Result.query.filter_by(**self.get_source_dict(thissource)).filter(Result.place > thisplace)
                                         .populate_existing().with_for_update()
                                         .order_by(Result.place).all())
                        
                        # bump this and later scanned bib order
                        thisorder = thisscannedbib.order
                        later_scannedbibs = (ScannedBib.query.filter_by(**self.get_source_dict(thissource)).filter(ScannedBib.order >= thisorder)
                                             .populate_existing().with_for_update()
                                             .all())
                        for scannedbib in later_scannedbibs:
                            scannedbib.order += 1
                        
                        # get all scanned bibs assigned to these results, including this one
                        scannedbibs_d = [thisscannedbib] + [r.scannedbib for r in later_results if r.had_scannedbib]
                        scannedbibs = iter(scannedbibs_d)
                        
                        # move all the scanned bibs to the later results; stop when we run out of scanned bibs
                        try:
                            for r in later_results:
                                r.scannedbib = next(scannedbibs)
                                r.had_scannedbib = True
                                
                        # stop when there are some results for which scanned bibs have not been assigned
                        except StopIteration:
                            pass
                        
                        # insert blank scanned bib at this result
                        scannedbib = ScannedBib(
                            bibno=BLANK_BIBNO,
                            order=thisorder,
                            **self.get_source_dict(thissource),
                        )
                        thisresult.scannedbib = scannedbib
                        
                    
                    # delete scanned bibno from current result
                    # shift scanned bibnos to earlier results
                    case 'delete':
                        # need greater than or equals to get this and all later results
                        results_d = (Result.query.filter_by(**self.get_source_dict(thissource)).filter(Result.place >= thisplace).order_by(Result.place)
                                     .populate_existing().with_for_update()
                                     .all())
                        results = iter(results_d)
                        
                        # get all scanned bibs assigned to these results, after this result
                        scannedbibs_d = [r.scannedbib for r in results_d[1:] if r.had_scannedbib]
                        scannedbibs = iter(scannedbibs_d)
                        
                        # move all the later scanned bibs to the results
                        # stop when we run out of scanned bibs or results
                        try:
                            for r in results:
                                r.scannedbib = next(scannedbibs)
                                r.had_scannedbib = True # probably not necessary as we're shifting earlier
                        
                        # we ran out of scanned bibs
                        except StopIteration:
                            # it should be ok to update only this r.scannedbib as we are only removing
                            # one scanned bib from the queue
                            r.scannedbib = None
                            r.had_scannedbib = False
                                        
                        # delete the scanned bib from the table
                        if thisscannedbib:
                            # update the order for the remaining scanned bibs
                            thisorder = thisscannedbib.order
                            scannedbibs_d = (ScannedBib.query.filter_by(**self.get_source_dict(thissource)).filter(ScannedBib.order > thisorder).order_by(ScannedBib.order)
                                             .populate_existing().with_for_update()
                                             .all())
                            for sb in scannedbibs_d:
                                sb.order = thisorder
                                thisorder += 1
                                
                            # remove this scanned bib from the database
                            db.session.delete(thisscannedbib)
                            current_app.logger.debug(f'deleted scannedbib id {thisscannedbib.id} bibno {thisscannedbib.bibno}')
                    
                # commit to db before unlocking
                db.session.commit()
            
            else:
                output_result = {'status' : 'success', 'error': error}
                
            # UNLOCK file access
            unlock(filelock)
            
            # return appropriate response
            return jsonify(output_result)

        except Exception as e:
            # UNLOCK file access
            unlock(filelock)

            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}

            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
