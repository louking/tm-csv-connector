"""websockets_server for tm_csv_connector
"""
# standard
from json import loads
from csv import DictWriter
from os.path import join

# pypi
from flask import current_app
from flask_sock import Sock
from loutilities.transform import Transform
from loutilities.timeu import timesecs
# from websockets import connect

# homegrown
from .model import db, Result, Setting
from .fileformat import filecolumns, db2file


_websockets = Sock()
# https://stackoverflow.com/a/24326540/799921
clienturi = 'ws://host.docker.internal:8081'

def init_app(app):
    _websockets.init_app(app)
    
@_websockets.route('/tm_reader')
def tm_reader(ws):
    while True:
        data = ws.receive()
        current_app.logger.debug(f'received data {data}')
        msg = loads(data)
        
        # get output file pathname
        filesetting = Setting.query.filter_by(name='output-file').one_or_none()
        if filesetting:
            filepath = join('/output_dir', filesetting.value)

        # handle messages from tm-reader-client
        opcode = msg.pop('opcode', None)
        if opcode in ['primary', 'select']:
            ## TODO: acquire LOCK here
            
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
                    current_app.logger.debug(f'appending to {filesetting.value}: {filedata["pos"]},{filedata["time"]}')
                    csvf = DictWriter(f, fieldnames=filecolumns, extrasaction='ignore')
                    csvf.writerow(filedata)
            
            ## TODO: release LOCK here
            
        # how did this happen?
        else:
            current_app.logger.error(f'unknown opcode received: {opcode}')
            
        