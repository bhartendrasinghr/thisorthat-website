"""Build the data the IPO checker reads.

Row shape is compact on purpose, because 541 records ship to a phone over a
video link: [symbol, name, listed, issue, listingGain, sinceIssue, perYear,
nifty, beatNifty, fromListingClose, adjustment]. Returns are fractions, not
percentages, so the page formats them one way in one place.

The issue price is the point of this dataset. Every other IPO page on the
site measures from the listing-day close, because the exchange bhavcopy is
all it has. The issue price is what an allottee actually paid, and the gap
between the two is where most of a hot IPO's gain sits before an ordinary
buyer can reach it. Both journeys are carried here, plus the Nifty over the
identical window so the comparison is like for like.

Regenerate with:  python3 build/ipo_checker.py [path/to/csv]
"""
import csv, json, os, sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/Downloads/nse_mainboard_ipos_2016_2026.csv')
OUT = os.path.join(ROOT, 'ipo-checker.json')
AS_OF = datetime(2026, 10, 29)

def num(v):
    v = (v or '').strip().replace(',', '')
    if not v: return None
    try: return float(v)
    except ValueError: return None

def tidy(n):
    for suf in (' Limited', ' Ltd.', ' Ltd'):
        if n.endswith(suf): return n[:-len(suf)]
    return n

rows, skipped = [], 0
for r in csv.DictReader(open(SRC, newline='', encoding='utf-8', errors='replace')):
    issue = num(r['Issue price (Rs)'])
    close = num(r['Listing-day close (Rs)'])
    now   = num(r['Price on 29-Oct-2026 (Rs, adjusted for bonus/split)'])
    nifty = num(r['Nifty 50 over same period %'])
    if not (issue and close and now) or issue <= 0 or close <= 0:
        skipped += 1; continue
    try: dt = datetime.strptime(r['Listing date'].strip(), '%Y-%m-%d')
    except ValueError: skipped += 1; continue

    ret  = now / issue - 1          # what an allottee got
    rfl  = now / close - 1          # what a listing-day buyer got
    lg   = num(r['Listing-day gain %'])
    cagr = num(r['Yearly return % (if listed 1y+)'])
    nr   = None if nifty is None else nifty / 100
    rows.append([
        r['NSE symbol'].strip(),
        tidy(r['Company'].strip()),
        r['Listing date'].strip(),
        round(issue, 2),
        None if lg is None else round(lg / 100, 4),
        round(ret, 4),
        None if cagr is None else round(cagr / 100, 4),
        nr if nr is None else round(nr, 4),
        # Use the sheet's own Beat Nifty? flag rather than recomputing ret > nr.
        # Recomputing gives 282 because one IPO sits on the boundary, and the
        # episode says 281. The page must not contradict what was said on camera.
        1 if (r.get('Beat Nifty?') or '').strip().lower() == 'yes' else 0,
        round(rfl, 4),
        (r['Adjustments'] or '').strip(),
    ])

rows.sort(key=lambda x: x[2], reverse=True)

def med(a):
    a = sorted(a); n = len(a)
    return a[n // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2

old3 = [x for x in rows if (AS_OF - datetime.strptime(x[2], '%Y-%m-%d')).days / 365.25 >= 3]
pops = [x[4] for x in rows if x[4] is not None]
summary = {
    'n': len(rows),
    'listed_up': sum(1 for p in pops if p > 0),
    'below_issue': sum(1 for x in rows if x[5] < 0),
    'beat_nifty': sum(x[8] for x in rows),
    'old3_n': len(old3),
    'old3_beat': sum(x[8] for x in old3),
    'median_pop': round(med(pops) * 100, 1),
    'median_since_issue': round(med([x[5] for x in rows]) * 100, 1),
    'doubled_day1': sum(1 for p in pops if p >= 1),
    'tenbagger': sum(1 for x in rows if x[5] >= 9),
    'halved': sum(1 for x in rows if x[5] <= -0.5),
}
json.dump({'_note': 'NSE mainboard IPOs, Feb 2016 to Oct 2026, prices 29 Oct 2026, adjusted '
                    'for bonus and split. SME listings excluded. Row: [symbol, name, listed, '
                    'issue, listingGain, sinceIssue, perYear, nifty, beatNifty, '
                    'fromListingClose, adjustment]. Returns are fractions.',
           'priced_at': '2026-10-29', 'summary': summary, 'rows': rows},
          open(OUT, 'w', encoding='utf-8'), separators=(',', ':'))

print(f'  {len(rows)} IPOs, {skipped} skipped')
for k, v in summary.items(): print(f'    {k:<20} {v}')
print(f'    pct beat (3y+)       {100*summary["old3_beat"]/summary["old3_n"]:.0f}%')
print(f'  {os.path.basename(OUT)}  {os.path.getsize(OUT):,} bytes')
