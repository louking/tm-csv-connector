'''
api - results api
=================================
'''

# standard
from traceback import format_exception_only, format_exc
from os.path import join

# pypi
from flask import session, request, current_app, jsonify
from flask.views import MethodView
from sqlalchemy import update, and_, select as sqlselect
from loutilities.timeu import timesecs

# homegrown
from . import bp
from ...model import db, Result, Setting, ScannedBib, Race
from ...fileformat import filelock, refreshfile

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
                bibno = msg['bibno'] if 'bibno' in msg else None
                race_id = msg['raceid']
                result = Result()
                result.bibno = bibno
                result.tmpos = msg['pos']
                result.time = timesecs(msg['time'])
                result.race_id = race_id
                result.place = place
                result.is_confirmed = False
                
                # check to see if a scanned bib is queued
                race = Race.query.filter_by(id=race_id).one()
                if race.next_scannedbib:
                    result.scannedbib = race.next_scannedbib
                    result.had_scannedbib = True
                    # check strictly greater than to find the next in the queue
                    next_scannedbib = ScannedBib.query.filter_by(race_id=race_id).filter(ScannedBib.order>race.next_scannedbib.order).order_by(ScannedBib.order.desc()).first()
                    # if None returned, this should work properly
                    race.next_scannedbib = next_scannedbib
                
                db.session.add(result)
                db.session.commit()
                
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


class PostBibApi(MethodView):
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
            
            # handle messages from barcode-scanner-client
            opcode = msg.pop('opcode', None)
            if opcode in ['scannedbib']:
                
                # determine place. if no records yet, create the output file
                lastrow = ScannedBib.query.filter_by(race_id=msg['raceid']).order_by(ScannedBib.order.desc()).first()
                if lastrow:
                    order = lastrow.order + 1
                else:
                    order = 1
                    
                # write to database
                bibno = msg['bibno']
                race_id = msg['raceid']
                scannedbib = ScannedBib()
                scannedbib.bibno = bibno
                scannedbib.race_id = race_id
                scannedbib.order = order
                db.session.add(scannedbib)
                db.session.flush()
                
                # update next result to use this scanned bib
                result = Result.query.filter_by(race_id=race_id, had_scannedbib=False).order_by(Result.place.asc()).first()
                if result:
                    result.scannedbib = scannedbib
                    result.had_scannedbib = True
                
                else:
                    # no result available to assign this scanned bib
                    race = Race.query.filter_by(id=race_id).one()
                    
                    # next_scannedbib is the next one to use; update if not set already
                    if not race.next_scannedbib:
                        race.next_scannedbib = scannedbib
                
                db.session.commit()
                
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
        
postbib_api = PostBibApi.as_view('_postbib')
bp.add_url_rule('/_postbib', view_func=postbib_api, methods=['POST',])


class SetParamsApi(MethodView):
    def post(self):
        try:
            form = request.form

            # skip race_changed because it's transient
            for key in form:
                if key == 'race_changed': continue
                session[f'_results_{key}'] = form[key]
            
            # rewrite csv file if race changed
            if 'race_changed' in form:
                # LOCK file access
                filelock.acquire()
                
                results = db.session.execute(
                    sqlselect(Result)
                    .where(and_(
                        Result.race_id == form['raceid'],
                        Result.is_confirmed == True)
                    )
                    .order_by(Result.place)
                ).all()
            
                # not sure why there is a need to for r[0] -- is this new in sqlalchemy 2.0?
                results = [r[0] for r in results]
                
                # rewrite the file
                refreshfile(results)
                
                # UNLOCK file access
                filelock.release()
                
            output_result = {'status' : 'success'}
            session.permanent = True

            return jsonify(output_result)

        except Exception as e:
            # UNLOCK file access
            filelock.release()

            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)

params_api = SetParamsApi.as_view('_setparams')
bp.add_url_rule('/_setparams', view_func=params_api, methods=['POST',])


class ScanActionApi(MethodView):
    def post(self):
        try:
            # options from home.scanned_bibno()
            options = request.form
            action = options['action']
            resultid = options['resultid']
            scanid = options['scanid']
            current_app.logger.debug(f'_scanaction: action={action} resultid={resultid} scanid={scanid}')
            
            # LOCK file access / place change / etc
            filelock.acquire()
            
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

                # save race and place for insert, delete
                thisrace = thisresult.race
                thisplace = thisresult.place

                # handle cases 
                match action:
                    # use the scanned bibno as bibno
                    case 'use':
                        thisresult.bibno = thisscannedbib.bibno
                    
                    # insert blank scanned bibno before current result
                    # shift scanned bibnos to later results
                    case 'insert':
                        # need strictly greater than thisplace to get the later results
                        later_results = Result.query.filter(Result.race == thisrace, Result.place > thisplace).order_by(Result.place).all()
                        
                        # get all scanned bibs assigned to these results, including this one
                        scannedbibs_d = [thisscannedbib] + [r.scannedbib for r in later_results if r.had_scannedbib]
                        scannedbibs = iter(scannedbibs_d)
                        
                        # insert blank scanned bib here
                        thisresult.scannedbib = None
                        
                        # move all the scanned bibs to the later results; stop when we run out of scanned bibs
                        try:
                            for r in later_results:
                                r.scannedbib = next(scannedbibs)
                                r.had_scannedbib = True
                                
                        # stop when there are some results for which scanned bibs have not been assigned
                        except StopIteration:
                            pass
                        
                        # we've gone through all the results
                        # if there are any remaining scanned bibs, the next one is the start of the scanned bib queue
                        else:
                            try:
                                next_scannedbib = next(scannedbibs)
                                thisrace.next_scannedbib = next_scannedbib
                            except StopIteration:
                                pass
                    
                    # delete scanned bibno from current result
                    # shift scanned bibnos to earlier results
                    case 'delete':
                        # need greater than or equals to get this and all later results
                        results = Result.query.filter(Result.race == thisrace, Result.place >= thisplace).order_by(Result.place).all()
                        
                        # get all scanned bibs assigned to these results, after this result
                        scannedbibs_d = [r.scannedbib for r in results[1:] if r.had_scannedbib]
                        
                        # we'll be iterating through these scanned bibs
                        scannedbibs = iter(scannedbibs_d)
                        
                        # move all the later scanned bibs to the results
                        # stop when we run out of scanned bibs or results
                        try:
                            for r in results:
                                r.scannedbib = next(scannedbibs)
                                r.had_scannedbib = True # probably not necessary as we're shifting earlier
                        
                        # we ran out of scanned bibs
                        except StopIteration:
                            # the next result's scanned bib was moved earlier
                            if thisrace.next_scannedbib:
                                r.scannedbib = thisrace.next_scannedbib
                                r.had_scannedbib = True
                                # may be more, remember it if it exists; note strictly greater than
                                previous_next = thisrace.next_scannedbib
                                next_scannedbib = ScannedBib.query.filter(ScannedBib.race==thisrace, ScannedBib.order>previous_next.order).order_by(ScannedBib.order).first()
                                thisrace.next_scannedbib = next_scannedbib
                                
                            else:
                                r.scannedbib = None
                                r.had_scannedbib = False
                        
                        # we finished going through the results
                        else:
                            # if there are any additional scanned bibs they need to be queued
                            try:
                                next_scannedbib = next(scannedbibs)
                                thisrace.next_scannedbib = next_scannedbib
                            
                            # no more scanned bibs => no queue
                            except StopIteration:
                                thisrace.next_scannedbib = None
                        
                # commit to db before unlocking
                db.session.commit()
            
            else:
                output_result = {'status' : 'success', 'error': error}
                
            # UNLOCK file access
            filelock.release()
            
            # return appropriate response
            return jsonify(output_result)

        except Exception as e:
            # UNLOCK file access
            filelock.release()

            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}

            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)

scanaction_api = ScanActionApi.as_view('_scanaction')
bp.add_url_rule('/_scanaction', view_func=scanaction_api, methods=['POST',])

