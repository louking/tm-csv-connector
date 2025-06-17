'''
times - time utility functions
=================================
'''
# standard
from datetime import timedelta

# pypi
from loutilities.timeu import asctime, timesecs

def asc2time(asctime):
    # print(f'asctime={asctime}, timesecs(asctime)={timesecs(asctime)}')
    return timesecs(asctime)

def time2asc(dbtime):
    timestr = str(timedelta(seconds=dbtime))
    wholefrac = timestr.split('.')
    if len(wholefrac) == 1:
        wholefrac.append('0')
    whole, frac = wholefrac
    frac = f'{round(int(frac)/10000):02}'
    return '.'.join([whole, frac])

