"""Turn the 541-IPO sheet into what the lookup page reads.

The sheet's one advantage over everything else on this site is the ISSUE
PRICE. Every other page here measures from the listing-day close, because
that is all the exchange bhavcopy gives. The issue price is what an allottee
actually paid, and the gap between those two numbers is the whole story of
an IPO: most of the gain happens before an ordinary buyer can get in.

So each row carries two journeys, not one:
  allotment  issue price  -> today
  open market listing close -> today
and the Nifty over the identical window, so the comparison is like for like.

Regenerate with:  python3 build/ipo_checker.py
"""
import csv, json, os, sys
from datetime import datetime

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/Downloads/nse_mainboard_ipos_2016_2026.csv')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'ipo-checker.json')

def num(v):
    v = (v or '').strip().replace(',', '')
    if not v: return None
    try: return float(v)
    except ValueError: return None

def tidy(name):
    for suf in (' Limited', ' Ltd.', ' Ltd'):
        if name.endswith(suf): return name[:-len(suf)]
    return name

rows, skipped = [], 0
for r in csv.DictReader(open(SRC, newline='', encoding='utf-8', errors='replace')):
    issue = num(r['Issue price (Rs)'])
    close = num(r['Listing-day close (Rs)'])
    now   = num(r['Price on 29-Oct-2026 (Rs, adjusted for bonus/split)'])
    if not (issue and close and now) or issue <= 0 or close <= 0:
        skipped += 1; continue
    d = r['Listing date'].strip()
    try: dt = datetime.strptime(d, '%Y-%m-%d')
    except ValueError: skipped += 1; continue
    yrs = (datetime(2026, 10, 29) - dt).days / 365.25
    rows.append({
        's': r['NSE symbol'].strip(),
        'n': tidy(r['Company'].strip()),
        'd': d,
        'i': round(issue, 2),            # issue price
        'l': round(close, 2),            # listing-day close
        'p': round(now, 2),              # today, adjusted
        'ar': round((now / issue - 1) * 100, 1),    # allottee return
        'mr': round((now / close - 1) * 100, 1),    # open-market return
        'ld': num(r['Listing-day gain %']),         # listing-day pop
        'nf': num(r['Nifty 50 over same period %']),
        'y': round(yrs, 2),
        'adj': (r['Adjustments'] or '').strip() or None,
    })

rows.sort(key=lambda x: x['d'], reverse=True)

ar = sorted(x['ar'] for x in rows)
def med(a): 
    n=len(a); return a[n//2] if n % 2 else (a[n//2-1]+a[n//2])/2

beat = sum(1 for x in rows if x['nf'] is not None and x['ar'] > x['nf'])
pops = [x['ld'] for x in rows if x['ld'] is not None]
summary = {
    'n': len(rows),
    'below_issue': sum(1 for x in rows if x['ar'] < 0),
    'beat_nifty': beat,
    'listed_up': sum(1 for p in pops if p > 0),
    'median_listing_pop': round(med(sorted(pops)), 1),
    'median_since_issue': round(med(ar), 1),
    'doubled_on_day1': sum(1 for p in pops if p >= 100),
    'tenbagger': sum(1 for x in rows if x['ar'] >= 900),
    'halved': sum(1 for x in rows if x['ar'] <= -50),
}
json.dump({'_note': 'NSE mainboard IPOs, Feb 2016 to Oct 2026. Prices 29 Oct 2026, '
                    'adjusted for bonus and split. Issue price is what an allottee paid; '
                    'listing close is the first price open to everyone else.',
           'priced_at': '2026-10-29', 'summary': summary, 'ipos': rows},
          open(OUT, 'w', encoding='utf-8'), separators=(',', ':'))

print(f'  {len(rows)} IPOs written, {skipped} skipped')
for k, v in summary.items(): print(f'    {k:<20} {v}')
print(f'  {OUT} ({os.path.getsize(OUT):,} bytes)')
