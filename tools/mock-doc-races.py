'''Creates mock races for the users-guide screenshots of the duplicate and unknown bib flags
(tm-csv-connector #158).

The races use the users-guide's use-case example (15 finishers, bibs 1680-1708, places 1-3
confirmed), so the new images match the existing ones. Each race has a chip-to-bib map for bibs
1680-1710 and is dated today. Running this again replaces races with the same names.

    zz docs duplicate bib   keypad entered 1692 at place 11 instead of 1693 (results-duplicate-bib.png)
    zz docs not in race     keypad dropped a digit at place 6, 169 instead of 1689 (results-not-in-race.png)
    zz docs double scan     1689 scanned twice (results-double-scan.png)
    zz docs all flags       all three together

The rows are inserted directly, so the output CSV isn't touched, but selecting one of these races
on the results page rewrites the CSV for it, as any race change does. Run it in the app container:

    docker cp tools/mock-doc-races.py tm-csv-connector-app-1:/tmp/
    MSYS_NO_PATHCONV=1 docker exec -w /app tm-csv-connector-app-1 sh -c 'PYTHONPATH=/app python /tmp/mock-doc-races.py'
'''
from datetime import date
from app import app
from tm_csv_connector.model import db, Race, Result, ScannedBib, ChipBib

TIMES = ['22:15.11', '23:02.84', '23:53.60', '23:56.49', '23:58.29', '24:36.88', '24:37.15', '24:39.58',
         '25:31.49', '25:38.58', '25:46.10', '26:04.39', '29:02.93', '30:04.04', '30:10.57']
BIBS = ['1680', '1682', '1685', '1684', '1687', '1689', '1688', '1696', '1695', '1692', '1693', '1701',
        '1706', '1708', None]
SCANS = ['1680', '1682', '1685', '1684', '1687', '1689', '1688', '1696', '1695', '1692', '1693', '1701',
         '1706', '1708']

def secs(t):
    m, s = t.split(':')
    return int(m) * 60 + float(s)

def mkrace(name, bibs, scans):
    old = Race.query.filter_by(name=name).one_or_none()
    if old:
        # results reference scans, so clear those before the cascade deletes both
        for r in old.results:
            r.scannedbib = None
        db.session.flush()
        db.session.delete(old)
        db.session.flush()
    race = Race(name=name, date=date.today(), start_time=8 * 3600, debounce_scans=True)
    db.session.add(race)
    db.session.flush()
    for bib in range(1680, 1711):
        db.session.add(ChipBib(race_id=race.id, tag_id=f'E28011{bib:06d}', bib=bib))
    scanobjs = []
    for order, scan in enumerate(scans, start=1):
        sb = ScannedBib(race_id=race.id, order=order, bibno=scan)
        db.session.add(sb)
        scanobjs.append(sb)
    for place, (bib, t) in enumerate(zip(bibs, TIMES), start=1):
        sb = scanobjs[place - 1] if place <= len(scanobjs) else None
        db.session.add(Result(race_id=race.id, tmpos=place, place=place, bibno=bib, time=secs(t),
                              is_confirmed=place <= 3, scannedbib=sb, had_scannedbib=sb is not None))
    db.session.commit()
    print(race.id, name)

with app.app_context():
    bibs = list(BIBS); bibs[10] = '1692'
    mkrace('zz docs duplicate bib', bibs, SCANS)

    bibs = list(BIBS); bibs[5] = '169'
    mkrace('zz docs not in race', bibs, SCANS)

    mkrace('zz docs double scan', BIBS, SCANS[:6] + ['1689'] + SCANS[6:])

    bibs = list(BIBS); bibs[10] = '1692'; bibs[5] = '169'
    mkrace('zz docs all flags', bibs, SCANS[:6] + ['1689'] + SCANS[6:])
