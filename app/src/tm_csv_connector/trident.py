"""trident chip read transformation
"""

# standard
from decimal import Decimal

# pypi
from sqlalchemy import select as sqlselect
from loutilities.timeu import asctime

# homegrown
from .model import db, ChipBib

datefmt = asctime('%y%m%d')
timefmt = asctime('%H%M%S')
Ymdfmt = asctime('%Y-%m-%d')

class Trident(object): pass

def tridentread2obj(line):
    # print(f'tridentread2obj({line})')
    trident = Trident()
    trident.reader_id = line[2]
    trident.receiver_id = line[3]
    trident.tag_id = line[4:16]
    trident.counter = int(line[16:20])
    trident.date = datefmt.asc2dt(line[20:26]).date()
    trident.time = Decimal(int(line[26:28])*3600 + int(line[28:30])*60 + int(line[30:32]) + int(line[32:34], 16)/100).quantize(Decimal('.01'))
    # trident.time = timefmt.asc2dt(line[26:32]).time()
    # trident.hundredths = int(line[32:34], 16)
    trident.rtype = line[36:38]

    # rssi may not be present, but should always be present for rtype=RR (raw read) records
    trident.rssi = None
    if len(line) > 38:
        trident.rssi = int(line[38:40], 16)

    # chip2bib mapping may not be available, but should be
    trident.bib = None
    chipbib = db.session.execute(
            sqlselect(ChipBib)
                .where(ChipBib.tag_id == trident.tag_id)
        ).one_or_none()
    if chipbib:
        chipbib = chipbib[0]
        trident.bib = chipbib.bib
        
    return trident

def tridentmarker2obj(line):
    trident = Trident()
    trident.reader_id = line[2]
    trident.date = datefmt.asc2dt(line[8:14]).date()
    trident.time = Decimal(int(line[16:18])*3600 + int(line[18:20])*60 + int(line[20:22]) + int(line[22:24], 16)/100).quantize(Decimal('.01'))
    # trident.time = timefmt.asc2dt(line[16:22]).time()
    # trident.hundredths = int(line[22:24], 16)
    trident.rtype = 'GUNTIME'
    return trident
