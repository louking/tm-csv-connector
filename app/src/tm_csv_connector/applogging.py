'''
applogging - define logging for the application
================================================
'''
# standard
from sys import stdout
from datetime import datetime
from logging import getLogger, DEBUG, StreamHandler, Formatter

# pypi
from flask import current_app
from loutilities.timeu import asctime

def setlogging():
    # ----------------------------------------------------------------------

    # this is needed for any INFO or DEBUG logging
    current_app.logger.setLevel(DEBUG)
    handler = StreamHandler(stdout)
    handler.setLevel(DEBUG)
    formatter = Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    current_app.logger.addHandler(handler)



def timenow():
    """useful for logpoints"""
    return asctime('%H:%M:%S.%f').dt2asc(datetime.now())
