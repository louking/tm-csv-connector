'''Summarizes a HAR file saved from the browser's dev console on the results page.

Prints the requests by url (count, median and max time), any errors, the gaps between results
polls, and each change in the results table's flagged rows (#158). HAR files of the results page
are tens of MB, so summarize them with this rather than reading them.

    python -I tools/summarize-har.py "<path>/2026-10-26 tm.localhost.har"

Use a real interpreter path on Windows, not the WindowsApps python stub.
'''
import json
import sys
from collections import defaultdict
from datetime import datetime
from statistics import median

def started(entry):
    return datetime.fromisoformat(entry['startedDateTime'].replace('Z', '+00:00'))

def main(path):
    with open(path, encoding='utf-8') as f:
        entries = json.load(f)['log']['entries']

    # requests by url
    byurl = defaultdict(list)
    for e in entries:
        byurl[(e['request']['method'], e['request']['url'].split('?')[0])].append(e)
    print(f'{len(entries)} requests')
    for (method, url), es in sorted(byurl.items(), key=lambda kv: -len(kv[1]))[:15]:
        times = [e['time'] for e in es]
        print(f'  {len(es):5d} {method or "ws":4s} {url}  median {median(times):.0f}ms, max {max(times):.0f}ms')

    # WebSockets show status 0, so leave them out
    errors = [e for e in entries if not e['request']['url'].startswith('ws')
              and e['response']['status'] not in (200, 304)]
    print(f'errors: {len(errors)}')
    for e in errors[:20]:
        print(f'  {started(e):%H:%M:%S} {e["response"]["status"]} {e["request"]["method"]} {e["request"]["url"]}')

    # results polls
    polls = [e for e in entries if e['request']['method'] == 'GET'
             and e['request']['url'].split('?')[0].endswith('/results/rest')]
    if not polls:
        return
    times = [started(e) for e in polls]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    print(f'results polls: {len(polls)}, {times[0]:%H:%M:%S} to {times[-1]:%H:%M:%S} UTC')
    if gaps:
        print(f'  gap median {median(gaps):.2f}s, max {max(gaps):.2f}s')
        long = [(times[i], g) for i, g in enumerate(gaps) if g > 2]
        for when, gap in long[:20]:
            print(f'  {gap:.1f}s gap after {when:%H:%M:%S}')

    # changes in the flagged rows; a HAR may not have kept every response body
    last = None
    for e in polls:
        body = e['response']['content'].get('text')
        if not body:
            continue
        rows = json.loads(body)
        flagged = [(r['placepos'], r['bibno'], ' '.join(c for c in r.get('DT_RowClass', '').split()
                                                       if c not in ('result-row', 'confirmed')))
                   for r in rows]
        flagged = [f for f in flagged if f[2]]
        if flagged != last:
            print(f'{started(e):%H:%M:%S} {len(rows)} rows, flagged (place, bib, flags): {flagged}')
            last = flagged

if __name__ == '__main__':
    main(sys.argv[1])
