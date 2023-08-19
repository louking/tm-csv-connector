"""websockets_server for tm_csv_connector
"""
# standard
from sys import stdout
from json import loads, dumps

# pypi
from flask import current_app
from flask_sock import Sock
from websockets.sync.client import connect

_websockets = Sock()
# https://stackoverflow.com/a/24326540/799921
clienturi = 'ws://host.docker.internal:8081'

async def send_to_client(msg):
    current_app.logger.debug(f'sending to {clienturi}: {msg}')
    async with connect(clienturi) as ws:
        await ws.send(dumps(msg))
    
def init_app(app):
    _websockets.init_app(app)
    
@_websockets.route('/tm_reader')
def tm_reader(ws):
    while True:
        data = ws.receive()
        msg = loads(data)
        current_app.logger.debug(f'received {msg}')
        