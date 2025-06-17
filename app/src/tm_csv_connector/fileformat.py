"""results csv output file management, including transformation from database formatting
"""
# standard
from threading import Lock
from os.path import join
from shutil import copyfile
from csv import DictWriter
from threading import get_native_id
from time import sleep

# pypi
from flask import current_app
from loutilities.transform import Transform
from loutilities.renderrun import rendertime

# homegrown
from .model import Setting

# test_lock is true only for testing
test_lock = False

# these names must match the message keys from tm-reader-client to the backend server
filecolumns = ['pos', 'bibno', 'time']

# provide lock for file update and multirow/multitable database manipulation
filelock = Lock()

# lock/unlock functions
def lock(thelock):
    thelock.acquire()

    # test lock
    if test_lock:
        current_app.logger.debug(f'thread {get_native_id()} sleeping in lock({thelock})')
        sleep(10)
        current_app.logger.debug(f'thread {get_native_id()} awake in lock({thelock})')

def unlock(thelock):
    thelock.release()
    
    if test_lock:
        current_app.logger.debug(f'thread {get_native_id()} unlocked in unlock({thelock})')
        

def fulltime(timesecs):
    """convert seconds to hh:mm:ss.dd

    Args:
        r (_type_): result in seconds

    Returns:
        string: hh:mm:ss.dd
    """
    thetime = rendertime(timesecs, 2)
    timesplit = thetime.split(':')
    
    # make sure hours, minutes, seconds
    while len(timesplit) < 3:
        timesplit = ['0'] + timesplit
    
    for i in range(0,2):
        timesplit[i] = f'{int(timesplit[i]):02d}'
    timesplit[2] = f'{float(timesplit[2]):05.2f}'

    return ':'.join(timesplit)
    

def db2file(result):
    """convert database result (elapsed time) to file dict (time of day)
    
    Args:
        result (model.Result): result as received from time machine (elapsed time)

    Returns:
        dict: result row for file, with time as time of day, see db2filet Transform
    """
    # if the result has a race, this is a normal result
    if result.race:
        tod_offset = result.race.start_time
    
    # if no race, this is a simulation result
    else:
        tod_offset = 0
    
    transform = {
        'pos': 'tmpos',
        'time': lambda r: fulltime(r.time + tod_offset),
        'bibno': 'bibno'
    }

    db2filet = Transform(transform, sourceattr=True, targetattr=False)

    resultrow = {}
    db2filet.transform(result, resultrow)

    return resultrow

def refreshfile(rows):
    """rewrite csv file
    
    NOTE: caller must acquire/release filelock

    Args:
        rows ([Result, ...]): list of Result rows to write, in place order
    """
    filesetting = Setting.query.filter_by(name='output-file').one_or_none()
    if filesetting:
        filepath = join('/output_dir', filesetting.value)
        
        # create temporary file
        from tempfile import TemporaryDirectory
        fdir = TemporaryDirectory()
        tmpfname = join(fdir.name, filesetting.value)
        with open(tmpfname, mode='w') as f:
            csvf = DictWriter(f, fieldnames=filecolumns, extrasaction='ignore')
            for row in rows:
                # this assumes when an unconfirmed row is encountered, no more rows should be sent to the file
                if not row.is_confirmed: break
                
                # write confirmed rows to the file
                rowdict = db2file(row)
                csvf.writerow(rowdict)

        # overwrite file
        current_app.logger.debug(f'overwriting {filesetting.value}')
        copyfile(tmpfname, filepath)
        fdir.cleanup()
            
