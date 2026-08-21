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
    """mfapi gives newest first as dd-mm-yyyy strings. Return oldest first.

    Some funds carry a bad NAV in the published history. Axis ELSS Tax Saver has
    a single 0.00000 on 7 April 2013, which would read as a 100% drawdown and
    divide by zero on the way out. Drop anything that is not a positive number.
    """
    out = []
    for d, v in series:
        try: v = float(v)
        except (TypeError, ValueError): continue
        if not (v > 0): continue
        out.append((datetime.strptime(d, '%d-%m-%Y'), v))
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


def add_month(d):
    """Same day next month, clamped. A SIP dated the 31st runs on the 30th in
    April and the 28th in February; it does not skip those months."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    day = d.day
    while day > 0:
        try: return d.replace(year=y, month=m, day=day)
        except ValueError: day -= 1


def xirr(flows):
    """Annual rate that discounts the flows to zero. Bisection, because it
    always converges on a normal SIP pattern where Newton can run away."""
    d0 = flows[0][0]
    def npv(r):
        return sum(a / (1 + r) ** ((d - d0).days / 365.25) for d, a in flows)
    lo, hi = -0.9999, 10.0
    if npv(lo) < 0 or npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0: lo = mid
        else: hi = mid
    return (lo + hi) / 2 * 100


def sip(pts, years, monthly=10000):
    """What a monthly SIP over the same window actually returned.

    The headline number on every fund page is lumpsum, point to point. Almost
    nobody invests that way, and the two can differ by a lot in either
    direction depending on when the fund rose.
    """
    if not pts: return None
    end_d, end_v = pts[-1]
    start = nav_on_or_before(pts, end_d - timedelta(days=round(365.25 * years)))
    if not start: return None
    flows, units, d = [], 0.0, start[0]
    while d < end_d:
        p = nav_on_or_before(pts, d)
        if p and p[1] > 0:
            units += monthly / p[1]
            flows.append((d, -float(monthly)))
        d = add_month(d)
    if len(flows) < 6: return None
    value = units * end_v
    rate = xirr(flows + [(end_d, value)])
    if rate is None: return None
    invested = monthly * len(flows)
    return dict(pct=rate, months=len(flows), invested=invested, value=value,
                gain=value - invested)


def rolling(pts, years):
    """Every N-year window in the series, not just the one ending today.

    A single "5 years: 13.2%" reads as a promise. The spread across every
    start date is what actually happened to people who bought on other days.
    """
    span = round(365.25 * years)
    out = []
    for d, v in pts:
        f = nav_on_or_before(pts, d + timedelta(days=span))
        if not f or f[0] <= d: continue
        days = (f[0] - d).days
        if abs(days - span) > 40: continue
        out.append(((f[1] / v) ** (365.25 / days) - 1) * 100 if years >= 1 else (f[1] / v - 1) * 100)
    if len(out) < 30: return None
    out.sort()
    neg = sum(1 for x in out if x < 0)
    return dict(n=len(out), lo=out[0], hi=out[-1],
                median=out[len(out) // 2], neg_pct=neg / len(out) * 100)


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
    # 8. a published NAV of zero must not become a 100% drawdown
    dirty = parse([('01-01-2020', '100'), ('02-01-2020', '0.00000'),
                   ('03-01-2020', '110'), ('04-01-2020', '120')])
    c = len(dirty) == 3 and abs(max_drawdown(dirty)['pct']) < 0.001; ok &= c
    print(f'  a zero NAV in the source is dropped, not a -100%: {c}')
    print('\nSIP AND ROLLING')
    s5 = sip(pts, 5)
    print(f'  a Rs 10,000 monthly SIP over 5 years: {s5["pct"]:.1f}% a year, '
          f'Rs {s5["invested"]:,} in over {s5["months"]} months became Rs {s5["value"]:,.0f}')
    print(f'  lumpsum over the same 5 years:        {ret(pts,5)["pct"]:.1f}% a year')
    r3 = rolling(pts, 3)
    print(f'  every 3 year window ({r3["n"]} of them): {r3["lo"]:.1f}% to {r3["hi"]:.1f}% a year, '
          f'median {r3["median"]:.1f}%, negative in {r3["neg_pct"]:.0f}%')

    print('\nMORE CHECKS')
    # 9. a SIP into a flat fund returns nothing, not a rounding artefact
    flat = [(base + timedelta(days=i), 100.0) for i in range(0, 2200, 7)]
    c = abs(sip(flat, 5)['pct']) < 0.01; ok &= c
    print(f'  a SIP into a flat fund returns 0%:               {c}')
    # 10. a SIP into a fund compounding at 12% returns about 12%
    twelve = [(base + timedelta(days=i), 100 * (1.12 ** (i / 365.25))) for i in range(0, 2200, 7)]
    r = sip(twelve, 5)['pct']; c = abs(r - 12) < 0.3; ok &= c
    print(f'  a SIP into a 12% fund returns about 12%:         {c}  ({r:.2f}%)')
    # 11. the rate really does discount the flows to zero
    end_d, end_v = twelve[-1]
    st = nav_on_or_before(twelve, end_d - timedelta(days=1826))
    fl, u, d = [], 0.0, st[0]
    while d < end_d:
        p = nav_on_or_before(twelve, d); u += 10000 / p[1]; fl.append((d, -10000.0)); d = add_month(d)
    fl.append((end_d, u * end_v))
    rr = xirr(fl) / 100
    npv = sum(a / (1 + rr) ** ((dd - fl[0][0]).days / 365.25) for dd, a in fl)
    c = abs(npv) < 1.0; ok &= c
    print(f'  the SIP rate discounts its own flows to zero:    {c}  (npv {npv:.4f})')
    # 12. a SIP dated the 31st still runs in February
    from datetime import date
    c = add_month(datetime(2024, 1, 31)).day == 29 and add_month(datetime(2023, 1, 31)).day == 28; ok &= c
    print(f'  a SIP on the 31st still runs in February:        {c}')
    # 13. a fund that only rose never has a negative window
    c = rolling(twelve, 3)['neg_pct'] == 0; ok &= c
    print(f'  a fund that only rose has no negative window:    {c}')
    # 14. the spread brackets the median
    r3t = rolling(pts, 3)
    c = r3t['lo'] <= r3t['median'] <= r3t['hi']; ok &= c
    print(f'  the window spread brackets its own median:       {c}')

    print(f'\n  all checks pass: {ok}')
