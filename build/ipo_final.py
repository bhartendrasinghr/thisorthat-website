"""Join listings to corporate actions and produce the finished dataset.

Ratio conventions, which are easy to get backwards:
  "Bonus 5:1"  = 5 free shares per 1 held, so 1 becomes 6 -> price factor 1/6
  "Bonus 1:1"  = 1 becomes 2                             -> 1/2
  "Split From Rs 10 To Rs 2" = 1 becomes 5               -> 2/10
Multiplying the listing price by the running product of these factors restates
it in today's share terms. Dividends are ignored: they need no price adjustment.
"""
import os, json, re, glob
from datetime import datetime
from collections import defaultdict

B = os.environ['BHAV']
listings = json.load(open(os.path.join(B, 'listings.json')))

acts = defaultdict(list)
seen = 0
for fn in glob.glob(os.path.join(B, 'ca', '*.json')):
    try: d = json.load(open(fn))
    except Exception: continue
    for r in (d if isinstance(d, list) else d.get('data', [])):
        isin = (r.get('isin') or '').strip()
        subj = (r.get('subject') or '')
        ex   = (r.get('exDate') or '').strip()
        if not isin or not ex: continue
        seen += 1
        f = None
        m = re.search(r'bonus\s+(\d+)\s*:\s*(\d+)', subj, re.I)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a + b > 0: f = b / (a + b)
        if f is None:
            m = re.search(r'from\s+rs?\.?\s*([\d.]+)\s*(?:/-)?\s*to\s+rs?\.?\s*([\d.]+)', subj, re.I)
            if m:
                frm, to = float(m.group(1)), float(m.group(2))
                if frm > 0 and to > 0 and to < frm: f = to / frm
        if f is None or not (0 < f < 1): continue
        try: exd = datetime.strptime(ex, '%d-%b-%Y').strftime('%Y%m%d')
        except ValueError: continue
        acts[isin].append((exd, round(f, 6), subj.strip()[:60]))

print(f"  {seen:,} corporate actions scanned, {len(acts):,} companies with a split or bonus")

LATEST = '20261001'
out = []
for r in listings:
    f, applied = 1.0, []
    for exd, fac, subj in sorted(acts.get(r['isin'], [])):
        if exd > r['listed']:
            f *= fac; applied.append({'ex': exd, 'factor': fac, 'what': subj})
    adj = r['listing_close'] * f
    if adj <= 0: continue
    ret = (r['now'] / adj - 1) * 100
    yrs = (datetime.strptime(LATEST, '%Y%m%d') - datetime.strptime(r['listed'], '%Y%m%d')).days / 365.25
    if yrs < 0.08: continue
    out.append({**{k: r[k] for k in ('isin','symbol','listed','listing_close','now')},
                'ca_factor': round(f, 6), 'adjusted_listing': round(adj, 2),
                'return_pct': round(ret, 1),
                'cagr_pct': round(((r['now']/adj) ** (1/yrs) - 1) * 100, 1),
                'years': round(yrs, 2), 'actions': applied,
                'unresolved_flag': bool(r['flags']) and not applied})
out.sort(key=lambda r: r['listed'])
json.dump(out, open(os.path.join(B, 'final.json'), 'w'), indent=1)

adj_n = len([r for r in out if r['ca_factor'] != 1.0])
unres = [r for r in out if r['unresolved_flag']]
print(f"  {len(out):,} listings priced   |   {adj_n} adjusted   |   {len(unres)} with an unexplained >25% day")

HAND = {'PAYTM':6.1,'NYKAA':-11.6,'POLICYBZR':-18.5,'STARHEALTH':-40.7,'LATENTVIEW':-52.0,
        'METROBRAND':68.9,'MEDPLUS':-41.6,'DATAPATTNS':463.1,'MAPMYINDIA':-39.3,
        'ANANDRATHI':1351.5,'SWIGGY':-47.8,'HYUNDAI':11.2,'OLAELEC':-59.3,
        'BAJAJHFL':-49.8,'NTPCGREEN':-25.1,'AWFIS':-44.2}
by = {r['symbol']: r for r in out}
ok = bad = 0
print("\n  --- cross-check against the 16 verified by hand ---")
for s, want in sorted(HAND.items()):
    r = by.get(s)
    if not r: print(f"    MISSING {s}"); bad += 1; continue
    d = abs(r['return_pct'] - want)
    if d <= 1.5: ok += 1
    else:
        bad += 1
        print(f"    DIFF {s:<12} hand {want:>8.1f}%  pipeline {r['return_pct']:>8.1f}%  factor {r['ca_factor']}")
print(f"    matched {ok}/16, differing {bad}")
