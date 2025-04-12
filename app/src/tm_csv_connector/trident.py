"""trident chip read transformation
"""

# standard
from decimal import Decimal

# pypi
from sqlalchemy import and_, select as sqlselect
from loutilities.timeu import asctime

# homegrown
from .model import db, ChipBib, ChipRead

datefmt = asctime('%y%m%d')
timefmt = asctime('%H%M%S')
Ymdfmt = asctime('%Y-%m-%d')

class Trident(object): pass

def tridentread2obj(raceid, line):
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
                .where(and_(
                    ChipBib.race_id == raceid,
                    ChipBib.tag_id == trident.tag_id,
                    )
                )
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

def trident2db(raceid, line, source):
    """Put line from trident reader into database. 
    Caller needs to commit

    Args:
        raceid (int): raceid to associate with this read
        line (raw): input line from Trident reader
        source (str): 'file' or 'live'
    """
    # only process chip reads (aa) or guntime (ab)
    if len(line) < 2 or line[0:2] not in ['aa', 'ab']: return
    
    # process read https://www.manula.com/manuals/tridentrfid/timemachine/1/en/topic/tag-data-message-format
    if line[0:2] == 'aa':
        tridentread = tridentread2obj(raceid, line.strip())
        reader_id = tridentread.reader_id
        receiver_id = tridentread.receiver_id
        tag_id = tridentread.tag_id
        counter = tridentread.counter
        date = tridentread.date
        time = tridentread.time
        rtype = tridentread.rtype
        rssi = tridentread.rssi
        bib = tridentread.bib

        # we might already have this record, if we're reading both filtered and raw chip files
        chipread = db.session.execute(
            sqlselect(ChipRead)
                .where(and_(
                    ChipRead.race_id == raceid,
                    ChipRead.reader_id == reader_id,
                    ChipRead.date == date,
                    ChipRead.tag_id == tag_id,
                    ChipRead.time == time,
                    )
                )
        ).one_or_none()
        
        # read not found, add row
        if not chipread:
            chipread = ChipRead(
                race_id=raceid,
                reader_id=reader_id,
                receiver_id=receiver_id,
                tag_id=tag_id,
                contig_ctr=counter,
                date=date,
                time=time,
                rssi=rssi,
                bib=bib,
                types=rtype,
                source=source,
            )
            db.session.add(chipread)
            db.session.flush()
        
        # read found, update types, possibly rssi, and bib
        else:
            chipread = chipread[0]
            types = chipread.types.split(',')
            if rtype not in types:
                types.append(rtype)
                types.sort()
            chipread.types = ','.join(types)
            
            if not chipread.rssi:
                chipread.rssi = rssi
            
            # this really shouldn't change, but if the
            # chipbib table was added after the fact this
            # will be used
            chipread.bib = bib
                
    # handle marker / start trigger
    elif line[0:2] == 'ab':
        tridentmarker = tridentmarker2obj(line.strip())
        reader_id = tridentmarker.reader_id
        date = tridentmarker.date
        time = tridentmarker.time
        rtype = tridentmarker.rtype

        # we might already have this record, if we're reading both filtered and raw chip files
        chipread = db.session.execute(
            sqlselect(ChipRead)
                .where(and_(
                    ChipRead.race_id == raceid,
                    ChipRead.reader_id == reader_id,
                    ChipRead.date == date,
                    ChipRead.time == time,
                    ChipRead.types == rtype,
                    )
                )
        ).one_or_none()
        
        # add if not there already; ignore if already there
        if not chipread:
            chipread = ChipRead(
                race_id=raceid,
                reader_id=reader_id,
                date=date,
                time=time,
                types=rtype,
                source=source,
            )
            db.session.add(chipread)
            db.session.flush()
