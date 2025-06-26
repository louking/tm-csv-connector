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
from ...model import db, Result, Setting, ScannedBib, Race, ChipBib, AppLog, BluetoothDevice
from ..common import PostBibApi, PostResultApi, ScanActionApi
from ...fileformat import filelock, refreshfile, lock, unlock
from ...trident import trident2db

class ParameterError(Exception): pass

class NormalPostResultApi(PostResultApi):
    def set_query(self):
        """initializes query parameters to retrieve Result records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        """
        msg = request.json
        
        return ([Result.race_id == msg['raceid']])
    
    def new_result(self):
        """format a Result record, setting time, simulationrun_id
        other fields are set by the PostResultApi post method

        Returns:
            Result()
        """
        msg = request.json

        result = Result()
        # result time comes in ascii format and must be converted to float
        result.time = timesecs(msg['time'])
        result.race_id = msg['raceid']
        return result

postresult_api = NormalPostResultApi.as_view('_postresult')
bp.add_url_rule('/_postresult', view_func=postresult_api, methods=['POST',])


class NormalPostBibApi(PostBibApi):
    def set_query(self):
        """initializes query parameters to retrieve ScannedBib records
        
        Returns:
            [filter list], suitable for .filter(*self.set_query())

        """
        msg = request.json
        
        return ([ScannedBib.race_id == msg['raceid']])
    
    def new_scannedbib(self):
        """format a ScannedBib record

        Returns:
            ScannedBib()
        """
        msg = request.json

        scannedbib = ScannedBib()
        scannedbib.race_id = msg['raceid']
        return scannedbib
        
postbib_api = NormalPostBibApi.as_view('_postbib')
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
                # current_app.logger.debug(f'setting session param _results_{key} to {form[key]}')
            
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


class NormalScanActionApi(ScanActionApi):
    def get_source(self, result):
        """initialize source item to use for filtering
        
        Arts:
            result (object): result item to use for filtering
            
        Returns:
            source item, suitable for .filter(source==source)

        """
        return result.race
    
    def get_source_dict(self, source):
        """initializes source dictionary
        
        Args:
            source (object): source item to use for filtering
            
        Returns:
            {source dict}, suitable for .filter_by(**self.get_source_dict()) or 

        """
        return {'race': source}

scanaction_api = NormalScanActionApi.as_view('_scanaction')
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


class GetBluetoothDevicesApi(MethodView):
    """get bluetooth device hardware addrs
    """
    def get(self):
        options = {}
        bluetoothdevices = db.session.execute(sqlselect(BluetoothDevice)).all()
        
        for bd in bluetoothdevices:
            bdtype = bd[0].type.type
            options.setdefault(bdtype, [])
            options[bdtype].append({'name': bd[0].name, 'hwaddr': bd[0].hwaddr})
        
        return jsonify(options)

getbluetoothdevices_api = GetBluetoothDevicesApi.as_view('_getbluetoothdevices')
bp.add_url_rule('/_getbluetoothdevices', view_func=getbluetoothdevices_api, methods=['GET'])
