"""Maintain mf-pulse-history.json: one row per month, as far back as AMFI goes.

Why this is a separate file from mf-pulse-data.json. That one is this month,
rebuilt from scratch every night. This one is the whole run of months, and it
is append only: once a month is in, it never changes, because AMFI does not
restate a published month. So it is committed to the repo and the nightly
build adds at most one row to it.

That matters for the build. Six years is about 75 spreadsheets. Downloading
them on every deploy would add minutes for no reason, and a cold cache would
make the site slow to ship. Instead the bootstrap runs once by hand, and
after that there is one new file a month.

  python3 build/mf_pulse_history.py            add any months that are missing
  python3 build/mf_pulse_history.py --from 2020-04   bootstrap from a date
  python3 build/mf_pulse_history.py --max 6    stop after six new months

Flows come from the monthly spreadsheet, which goes back years. SIP comes
from the monthly note PDFs, which AMFI lists only from June 2024, and each
note carries a seven month table, so a handful of notes covers the lot.
"""
import json, os, re, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'mf-pulse-history.json')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mf_pulse_refresh import (                                  # noqa: E402
    cached, get, month_file, parse_month, parse_sip, segment, back, eom,
)

MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


def key(d):
    return f'{d:%Y-%m}'


def load():
    if os.path.exists(TARGET):
        return json.load(open(TARGET, encoding='utf-8'))
    return {'months': [], 'sip': {}, 'notes_read': []}


def flows_for(d):
    """One month's five flow lines plus assets, or None if not published."""
    data = parse_month(cached(month_file(d), f'https://portal.amfiindia.com/spages/{month_file(d)}'))
    ind = segment(data, 'industry')
    if not ind.get('aum'):
        return None
    return {
        'm': key(d),
        'aum': round(ind['aum'], 2),
        'equity': round(segment(data, 'equity').get('flow') or 0, 2),
        'debt': round(segment(data, 'debt').get('flow') or 0, 2),
        'hybrid': round(segment(data, 'hybrid').get('flow') or 0, 2),
        'passive': round(segment(data, 'passive').get('flow') or 0, 2),
        'total': round(ind.get('flow') or 0, 2),
        'folios': int(ind['folios']) if ind.get('folios') else None,
    }


def sip_from_notes(have, tried, limit=40):
    """Every SIP figure AMFI's notes carry, merged into one month->row map.

    Each note prints the last seven months, so the notes overlap heavily and
    a dozen of them cover several years. Where two notes disagree about the
    same month the newer one wins, because AMFI occasionally tidies a figure
    in a later note and the later print is the one it stands behind.
    """
    try:
        listing = json.loads(get('https://www.amfiindia.com/api/amfi-monthly-note', timeout=45))
    except Exception as e:
        print(f'  could not list the notes: {e}')
        return have

    items = []
    for fy in listing.get('data', []):
        for it in fy.get('items', []):
            m = re.match(r'([a-z]+)-(\d{4})', (it.get('monthtitle') or '').strip().lower())
            if m and m.group(1)[:3] in MONTHS and it.get('pdfurl'):
                items.append((date(int(m.group(2)), MONTHS[m.group(1)[:3]], 1), it['pdfurl']))
    items.sort()                      # oldest first, so newer notes overwrite

    added = 0
    newest = items[-1][0] if items else None
    for d, url in items[-limit:]:
        want = key(d)
        # Five of AMFI's older notes word the SIP table in a way nothing here
        # recognises, and they never will: retrying them would re-download a
        # few megabytes of PDF on every build to fail again. Remember what has
        # been opened and move on. The newest note is always re-read, since
        # that is the one that changes.
        if want in tried and d != newest:
            continue
        if want in have and all(key(back(d, i)) in have for i in range(7)):
            tried.append(want)
            continue
        tried.append(want)
        try:
            sip = parse_sip(cached(f'note-{d:%Y-%m}.pdf', url, timeout=120), d)
        except Exception as e:
            print(f'  note {d:%b %Y}: {e}')
            continue
        if not sip or not sip.get('contribution'):
            print(f'  note {d:%b %Y}: the SIP table did not parse')
            continue
        for i, label in enumerate(sip.get('months') or []):
            mm = re.match(r'([A-Z][a-z]{2})-(\d{2})', label)
            if not mm:
                continue
            mk = f'20{mm.group(2)}-{MONTHS[mm.group(1).lower()]:02d}'
            acc = sip.get('accounts') or []
            row = {'contribution': sip['contribution'][i] if i < len(sip['contribution']) else None,
                   'accounts': acc[i] if i < len(acc) else None}
            if sip.get('assets') and i < len(sip['assets']):
                row['assets'] = sip['assets'][i]
            if row['contribution'] is not None:
                if mk not in have:
                    added += 1
                have[mk] = row
        print(f'  note {d:%b %Y}: {len(sip.get("months") or [])} months read')
    print(f'  SIP: {len(have)} months on file, {added} new')
    return have


def main(argv):
    start = None
    limit = 6
    for i, a in enumerate(argv):
        if a == '--from' and i + 1 < len(argv):
            y, m = argv[i + 1].split('-')
            start = date(int(y), int(m), 1)
        if a == '--max' and i + 1 < len(argv):
            limit = int(argv[i + 1])

    doc = load()
    have = {r['m'] for r in doc['months']}
    if start is None:
        # Normal nightly case: just reach back far enough to catch up if a
        # run was missed, rather than re-walking six years every time.
        start = back(date.today().replace(day=1), 14)

    wanted, d = [], start
    today = date.today().replace(day=1)
    while d <= today:
        if key(d) not in have:
            wanted.append(d)
        d = back(d, -1)

    print(f'→ {len(doc["months"])} months on file, {len(wanted)} to try '
          f'(stopping after {limit})')
    added = 0
    for d in wanted:
        if added >= limit:
            print(f'  stopping at {limit}; run again to continue')
            break
        try:
            row = flows_for(d)
        except Exception as e:
            print(f'  {d:%b %Y}: {e}')
            continue
        if not row:
            continue
        doc['months'].append(row)
        added += 1
        print(f'  {d:%b %Y}: AUM {row["aum"]/1e5:.2f} L cr, equity {row["equity"]:+,.0f} cr')

    doc['months'].sort(key=lambda r: r['m'])
    tried = doc.get('notes_read') or []
    doc['sip'] = sip_from_notes(doc.get('sip') or {}, tried)
    doc['notes_read'] = sorted(set(tried))
    doc['generated'] = date.today().isoformat()
    doc['first'] = doc['months'][0]['m'] if doc['months'] else None
    doc['last'] = doc['months'][-1]['m'] if doc['months'] else None

    # A run of months with a hole in it draws a chart that lies about the
    # shape of the line, so say so rather than plotting it quietly.
    seen = [r['m'] for r in doc['months']]
    gaps = []
    for i in range(1, len(seen)):
        y0, m0 = map(int, seen[i - 1].split('-'))
        y1, m1 = map(int, seen[i].split('-'))
        if (y1 - y0) * 12 + (m1 - m0) != 1:
            gaps.append(f'{seen[i-1]} to {seen[i]}')
    doc['gaps'] = gaps
    if gaps:
        print(f'  WARNING: {len(gaps)} gap(s) in the run: ' + ', '.join(gaps[:5]))

    json.dump(doc, open(TARGET, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(TARGET) / 1024
    print(f'\n  {len(doc["months"])} months ({doc["first"]} to {doc["last"]}), '
          f'{len(doc["sip"])} with SIP, {size:.0f} KB')


if __name__ == '__main__':
    main(sys.argv[1:])
