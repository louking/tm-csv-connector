"""websockets for tm_csv_connector
"""
# standard
from json import loads

# pypi
from flask_sock import Sock

websockets = Sock()

@websockets.route('/tm_reader')
def tm_reader(ws):
    while True:
        data = ws.receive()
        msg = loads(data)
        print(msg)
        