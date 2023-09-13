"""file columns definition, including transformation from database formatting
"""
# standard
from threading import Lock

# homegrown
from loutilities.transform import Transform
from loutilities.renderrun import rendertime

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
    
db2file = Transform({
    'pos': 'tmpos',
    'time': lambda r: fulltime(r.time),
    'bibno': 'bibno'
}, sourceattr=True, targetattr=False)
