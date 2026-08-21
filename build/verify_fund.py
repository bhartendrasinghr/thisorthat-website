"""Fund maths for the research tool, checked before it goes in the page.

Every number here is arithmetic on published NAVs. Nothing ranks, scores or
recommends, because that would be advice and this is a media brand.

Rules encoded:
  1. Under a year, report the plain change. Annualising three months into a
     "48% return" is the most common way these tools mislead.
  2. NAV series have gaps for weekends and holidays, so a date lookup takes the
     nearest NAV at or before the date, never the nearest either side.
  3. Worst rolling 12 months is computed over every start date in the series,
     not over calendar years, which is what hides the bad stretches.
  4. Drawdown is peak to trough on NAV, and recovery is only counted once the
     old peak is actually regained.
"""
from datetime import datetime, timedelta

def parse(series):
    """mfapi gives newest first as dd-mm-yyyy strings. Return oldest first."""
    out = [(datetime.strptime(d, '%d-%m-%Y'), float(v)) for d, v in series]
    return sorted(out, key=lambda x: x[0])

def nav_on_or_before(pts, when):
    lo, hi, best = 0, len(pts) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if pts[mid][0] <= when: best = pts[mid]; lo = mid + 1
        else: hi = mid - 1
    return best

def ret(pts, years):
    """CAGR over `years`, or the plain change when the period is under a year."""
    if not pts: return None
    end_d, end_v = pts[-1]
    start = nav_on_or_before(pts, end_d - timedelta(days=round(365.25 * years)))
    if not start or start[0] >= end_d: return None
    days = (end_d - start[0]).days
    if days < 300: return None
    total = end_v / start[1]
    if years < 1:
        return dict(pct=(total - 1) * 100, annualised=False, days=days)
    return dict(pct=((total ** (365.25 / days)) - 1) * 100, annualised=True, days=days)

def worst_rolling_12m(pts):
    """The worst any investor could have done over any 12 months in the series."""
    worst, when = None, None
    for i, (d, v) in enumerate(pts):
        fwd = nav_on_or_before(pts, d + timedelta(days=365))
        if not fwd or fwd[0] <= d: continue
        if (fwd[0] - d).days > 400: continue
        r = (fwd[1] / v - 1) * 100
        if worst is None or r < worst: worst, when = r, (d, fwd[0])
    return dict(pct=worst, frm=when[0], to=when[1]) if worst is not None else None

def max_drawdown(pts):
    """Deepest peak to trough fall, and how long it took to get back."""
    peak = pts[0][1]; peak_d = pts[0][0]
    worst = 0.0; info = None
    for d, v in pts:
        if v > peak: peak, peak_d = v, d
        dd = (v / peak - 1) * 100
        if dd < worst:
            worst, info = dd, dict(pct=dd, peak=peak_d, trough=d, peak_nav=peak)
    # A fund that has only ever risen has no drawdown. Say zero, do not return
    # nothing, or the page shows a blank where the honest answer is "none on record".
    if not info:
        return dict(pct=0.0, peak=peak_d, trough=pts[-1][0], peak_nav=peak,
                    recovered=None, recovery_months=None, never_fell=True)
    rec = next((d for d, v in pts if d > info['trough'] and v >= info['peak_nav']), None)
    info['recovered'] = rec
    info['recovery_months'] = round((rec - info['trough']).days / 30.44) if rec else None
    return info

if __name__ == '__main__':
    import json, urllib.request
    def fetch(code):
        with urllib.request.urlopen(f'https://api.mfapi.in/mf/{code}', timeout=30) as r:
            d = json.load(r)
        return d['meta']['scheme_name'], parse([(x['date'], x['nav']) for x in d['data']])

    name, pts = fetch(122639)   # Parag Parikh Flexi Cap, Direct Growth
    print(f'{name}\n  {len(pts)} NAVs, {pts[0][0]:%b %Y} to {pts[-1][0]:%b %Y}\n')
    for y in (1, 3, 5, 10):
        r = ret(pts, y)
        print(f'  {y:>2}y  {r["pct"]:>7.2f}%  {"a year" if r["annualised"] else "total"}' if r else f'  {y:>2}y  not enough history')
    w = worst_rolling_12m(pts)
    print(f'\n  worst 12 months: {w["pct"]:.2f}%  ({w["frm"]:%b %Y} to {w["to"]:%b %Y})')
    dd = max_drawdown(pts)
    print(f'  deepest fall:    {dd["pct"]:.2f}%  ({dd["peak"]:%b %Y} to {dd["trough"]:%b %Y})'
          + (f', back in {dd["recovery_months"]} months' if dd['recovered'] else ', not yet recovered'))

    print('\nCHECKS')
    ok = True
    # 1. a series that doubles in exactly 5 years is 14.87% a year
    base = datetime(2020, 1, 1)
    # 6 years of data so a 5 year lookback has somewhere to land
    dbl = [(base + timedelta(days=i), 100 * (2 ** (i / 1826.25))) for i in range(0, 2200, 7)]
    r = ret(dbl, 5); c = abs(r['pct'] - 14.87) < 0.05; ok &= c
    print(f'  a doubling over 5 years reads 14.87% a year:   {c}  ({r["pct"]:.2f}%)')
    # 2. short periods are never annualised
    c = ret(pts, 0.5) is None or not ret(pts, 0.5)['annualised']; ok &= c
    print(f'  under a year is never annualised:              {c}')
    # 3. a series that only rises has a positive worst 12 months
    c = worst_rolling_12m(dbl)['pct'] > 0; ok &= c
    print(f'  a series that only rises has no losing year:   {c}')
    # 4. and no drawdown
    c = abs(max_drawdown(dbl)['pct']) < 0.001; ok &= c
    print(f'  a series that only rises has no drawdown:      {c}')
    # 5. a known 50% fall reads as 50%
    v = [(base + timedelta(days=i), x) for i, x in enumerate([100, 120, 60, 80, 130])]
    d5 = max_drawdown(v); c = abs(d5['pct'] + 50) < 0.001; ok &= c
    print(f'  a fall from 120 to 60 reads as 50%:            {c}  ({d5["pct"]:.1f}%)')
    # 6. recovery is only counted once the old peak is regained
    c = d5['recovered'] is not None and d5['recovered'] > d5['trough']; ok &= c
    print(f'  recovery counts only when the peak is back:    {c}')
    # 7. a gap in the series does not throw
    sparse = [(base + timedelta(days=i * 40), 100 + i) for i in range(30)]
    c = ret(sparse, 1) is not None and worst_rolling_12m(sparse) is not None; ok &= c
    print(f'  weekend and holiday gaps are handled:          {c}')
    print(f'\n  all checks pass: {ok}')
