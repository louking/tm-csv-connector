"""file management, including transformation from database formatting
"""
# standard
from threading import Lock
from os.path import join
from shutil import copy
from csv import DictWriter

# pypi
from flask import current_app
from loutilities.transform import Transform
from loutilities.renderrun import rendertime

# homegrown
from .model import Setting

# these names must match the message keys from tm-reader-client to the backend server
filecolumns = ['pos', 'bibno', 'time']

# provide lock for file update
filelock = Lock()

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
    tod_offset = result.race.start_time
    
    db2filet = Transform({
        'pos': 'tmpos',
        'time': lambda r: fulltime(r.time + tod_offset),
        'bibno': 'bibno'
    }, sourceattr=True, targetattr=False)

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
        copy(tmpfname, filepath)
        fdir.cleanup()
            
