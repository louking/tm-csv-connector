"""websockets_server for tm_csv_connector
"""
# standard
from sys import stdout
from json import loads, dumps

# pypi
from flask import current_app, session
from flask_sock import Sock
from loutilities.timeu import timesecs
# from websockets import connect

# homegrown
from .model import db, Result

_websockets = Sock()
# https://stackoverflow.com/a/24326540/799921
clienturi = 'ws://host.docker.internal:8081'

# async def send_to_client(msg):
#     current_app.logger.debug(f'sending to {clienturi}: {msg}')
#     async with connect(clienturi) as ws:
#         await ws.send(dumps(msg))
    
def init_app(app):
    _websockets.init_app(app)
    
@_websockets.route('/tm_reader')
def tm_reader(ws):
    while True:
        data = ws.receive()
        current_app.logger.debug(f'received data {data}')
        msg = loads(data)
        # current_app.logger.debug(f'received msg {msg}')
        
        # handle messages from tm-reader-client
        opcode = msg.pop('opcode', None)
        if opcode in ['primary', 'select']:
            # write to database
            result = Result()
            result.bibno = msg['bibno'] if 'bibno' in msg else None
            result.tmpos = msg['pos']
            result.time = timesecs(msg['time'])
            result.race_id = msg['raceid']
            db.session.add(result)
            db.session.commit()
            
        # how did this happen?
        else:
            current_app.logger.error(f'unknown opcode received: {opcode}')
            
        