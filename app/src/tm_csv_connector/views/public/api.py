'''
api - results api
=================================
'''

# standard
from traceback import format_exception_only, format_exc
from os.path import join
from os import remove
from uuid import uuid4
from csv import DictReader
from datetime import datetime

# pypi
from flask import session, request, current_app, jsonify
from flask.views import MethodView
from sqlalchemy import and_, select as sqlselect
from loutilities.timeu import timesecs

# homegrown
from . import bp
from ...model import db, Result, Setting, ScannedBib, Race, ChipBib, AppLog
from ...fileformat import filelock, refreshfile, lock, unlock
from ...trident import trident2db

class ParameterError(Exception): pass

class PostResultApi(MethodView):
    """receive a result from tm-reader-client
    """
    def post(self):
        try:
            ## LOCK file access
            lock(filelock)
            
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
            unlock(filelock)
            return jsonify(status='success')

        except Exception as e:
            ## UNLOCK file access
            unlock(filelock)
            
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
    """receive a scanned bibno from barcode-scanner-client
    """
    def post(self):
        try:
            ## LOCK file access
            lock(filelock)
            
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
            unlock(filelock)
            return jsonify(status='success')

        except Exception as e:
            ## UNLOCK file access
            unlock(filelock)
            
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
postbib_api = PostBibApi.as_view('_postbib')
bp.add_url_rule('/_postbib', view_func=postbib_api, methods=['POST',])


class ChipReadsApi(MethodView):
    """upload chip reads from file

    Raises:
        ParameterError: _description_
    """
    ALLOWED_EXTENSIONS = ['log']
    
    def get(self):
        # this returns initial values for the form, should be empty because the
        # input form doesn't have any initial values
        return jsonify({})
    
    def allowed_filename(self, filename):
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
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
                raceid = request.form['data[keyless][race]']
                if not raceid:
                    return jsonify(status='fail', error='please choose a race')
            
                filepath = join('/tmp', request.form['data[keyless][file]'])
                with open(filepath, 'r') as stream:
                    # read to end of file
                    for line in stream:
                        trident2db(raceid, line, 'file')
                    
                # delete temporary file, commit changes to database and declare success
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
        
chipreads_api = ChipReadsApi.as_view('_chipreads')
bp.add_url_rule('/_chipreads/rest', view_func=chipreads_api, methods=['POST','GET'])


class LiveChipReadsApi(MethodView):
    """receive chip read from trident-reader-client
    """
    
    def post(self):
        try:
            raceid = request.json['raceid']
            data = request.json['data']
            lines = data.split('\r\n')
            for line in lines:
                trident2db(raceid, line, 'live')
            db.session.commit()
            return jsonify(status='success')
                
        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
livechipreads_api = LiveChipReadsApi.as_view('_livechipreads')
bp.add_url_rule('/_livechipreads', view_func=livechipreads_api, methods=['POST'])


class Chip2BibApi(MethodView):
    """import chip to bibno mapping from csv file

    Raises:
        ParameterError: invalid action -- logic error
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
            
            elif action == 'edit':
                race_id = request.form['data[keyless][race]']
                if not race_id:
                    return jsonify(status='fail', error='please choose a race')
                
                filepath = join('/tmp', request.form['data[keyless][file]'])
                with open(filepath, 'r') as csvfile:
                    csv = DictReader(csvfile)
                    # read to end of file
                    for row in csv:
                        chip = row['chip']
                        bib  = row['bib']
                        chipbib = db.session.execute(
                            sqlselect(ChipBib)
                                .where(and_(
                                    ChipBib.race_id == race_id,
                                    ChipBib.tag_id == chip,
                                    )
                                )
                        ).one_or_none()
                        
                        if not chipbib:
                            chipbib = ChipBib(
                                race_id = race_id,
                                tag_id = chip,
                                bib    = bib,
                            )
                            db.session.add(chipbib)
                            db.session.flush()
                            
                        # this could happen a) if file reloaded, or b) if a new
                        # set of chips is used with overlapping chip numbers
                        else:
                            chipbib = chipbib[0]
                            chipbib.bib = bib
                    
                # delete temporary file, commit changes to database and declare success
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
        
chip2bib_api = Chip2BibApi.as_view('_chip2bib')
bp.add_url_rule('/_chip2bib/rest', view_func=chip2bib_api, methods=['POST','GET'])


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
                lock(filelock)
                
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
                unlock(filelock)
                
            output_result = {'status' : 'success'}
            session.permanent = True

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

params_api = SetParamsApi.as_view('_setparams')
bp.add_url_rule('/_setparams', view_func=params_api, methods=['POST',])


class ScanActionApi(MethodView):
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

scanaction_api = ScanActionApi.as_view('_scanaction')
bp.add_url_rule('/_scanaction', view_func=scanaction_api, methods=['POST',])


class ChipReaderStatusApi(MethodView):
    
    def post(self):
        try:
            readerstatus = request.json
            status = readerstatus['status']
            reader_id = readerstatus['reader_id']
            
            # NOTE: we should only be receiving status changes
            # these cases must match those in results.js
            match status:
                case 'disconnected':
                    statustxt = f'chip reader {reader_id} disconnected'
                case 'connected':
                    statustxt = f'chip reader {reader_id} connected'
                case 'network-unreachable':
                    statustxt = f'chip reader {reader_id} network unreachable'
                case 'no-response':
                    statustxt = f'chip reader {reader_id} not responding'
                case '_':
                    raise ParameterError(f'received invalid message for chip reader {reader_id}')
            
            current_app.logger.info(statustxt)
            db.session.add(AppLog(time=datetime.now(), info=statustxt))
            db.session.commit()
            
            return jsonify(status='success')
                
        except Exception as e:
            # report exception
            exc = ''.join(format_exception_only(type(e), e))
            output_result = {'status' : 'fail', 'error': 'exception occurred:<br>{}'.format(exc)}
            
            # roll back database updates and close transaction
            db.session.rollback()
            current_app.logger.error(format_exc())
            return jsonify(output_result)
        
chipreaderstatus_api = ChipReaderStatusApi.as_view('_chipreaderstatus')
bp.add_url_rule('/_chipreaderstatus', view_func=chipreaderstatus_api, methods=['POST'])


class GetRacesApi(MethodView):
    """get races for select field
    """
    def get(self):
        options = []
        # sort most recent race first
        races = Race.query.order_by(Race.date.desc()).all()
        for r in races:
            option = {'value': r.id, 'label': r.raceyear}
            options.append(option)
        
        return jsonify(options)

getraces_api = GetRacesApi.as_view('_getraces')
bp.add_url_rule('/_getraces', view_func=getraces_api, methods=['GET'])
