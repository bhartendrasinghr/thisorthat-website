"""Multi Cap vs Flexi Cap: what the rulebook says, and what the funds actually hold.

SEBI publishes what each category MUST hold. What a fund ACTUALLY holds sits in
monthly portfolio disclosures scattered across ~45 AMC websites, which is the bit
data vendors charge for. The NAV is free and daily, so this recovers the implied
cap mix from the one public input, using returns-based style analysis (Sharpe 1992):
find the blend of large / mid / small cap that best tracks the fund's weekly returns,
weights non-negative and summing to one so the answer reads as a portfolio.

The method is only worth trusting if it can recover a mandate it should already
know, so the sanity gate below runs it on Large, Mid and Small Cap funds first.
Those are mandated to hold 80% / 65% / 65% of their own segment. If the gate does
not clear, the script refuses to write anything.

Regenerate with:  python3 build/cap_mix.py
"""
import json, statistics as st, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATS = ['Multi Cap Fund', 'Flexi Cap Fund', 'Large Cap Fund', 'Mid Cap Fund', 'Small Cap Fund']
WEEKS = 1096                      # three years, the widest window with good coverage everywhere
RULE_DEADLINE = datetime(2021, 1, 31)   # multi caps had to comply one month after AMFI's Jan 2021 list


# ─── NAV loading ──────────────────────────────────────────────────────────
def parse(series):
    """Drop anything that is not a positive number. Some series carry a 0.00000,
    which would read as a total wipeout and divide by zero on the way out."""
    out = []
    for d, v in series:
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if not (v > 0):
            continue
        out.append((datetime.strptime(d, '%d-%m-%Y'), v))
    return sorted(out, key=lambda x: x[0])


# mfapi rejects Python's default User-Agent with a 502, so send a real one.
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ThisOrThat-build/1.0'
CACHE = ROOT / 'build' / '.navcache'


def fetch(item):
    """One fund's NAV history, from the local cache when we already have it.
    The cache keeps a rebuild from hammering a free API, and keeps the numbers
    reproducible on a day the API is having trouble."""
    name, code = item
    hit = CACHE / f'{code}.json'
    if hit.exists():
        try:
            pts = parse(json.loads(hit.read_text(encoding='utf-8')))
            if len(pts) >= 400:
                return {'name': name, 'pts': pts}
        except Exception:
            pass

    for attempt in range(3):
        try:
            req = urllib.request.Request(f'https://api.mfapi.in/mf/{code}', headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
            rows = [[x['date'], x['nav']] for x in j['data']]
            pts = parse(rows)
            if len(pts) < 400:
                return None
            CACHE.mkdir(exist_ok=True)
            hit.write_text(json.dumps(rows), encoding='utf-8')
            return {'name': name, 'pts': pts}
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def load():
    idx = json.load(open(ROOT / 'fund-index.json'))
    store = {}
    for cat in CATS:
        i = idx['cats'].index(cat)
        codes = [(f[0], f[3]) for f in idx['funds'] if f[2] == i and f[3]]
        with ThreadPoolExecutor(8) as ex:
            store[cat] = [x for x in ex.map(fetch, codes) if x]
        print(f'  {cat:<16} history for {len(store[cat])} of {len(codes)}')
    return store


# ─── series maths ─────────────────────────────────────────────────────────
def on_or_before(pts, when):
    lo, hi, got = 0, len(pts) - 1, None
    while lo <= hi:
        m = (lo + hi) // 2
        if pts[m][0] <= when:
            got = pts[m]; lo = m + 1
        else:
            hi = m - 1
    return got


def weekly(pts, start, end):
    """Weekly returns on a fixed seven-day grid, so every fund in the comparison
    is sampled on exactly the same dates and the fits stay comparable."""
    out, d = [], start
    prev = on_or_before(pts, d)
    if not prev:
        return None
    while d <= end:
        d += timedelta(days=7)
        cur = on_or_before(pts, d)
        if not cur or cur[0] <= prev[0]:
            continue
        out.append(cur[1] / prev[1] - 1)
        prev = cur
    return out


def composite(funds, start, end):
    """Equal weighted category index: the median fund's return each week.
    Median rather than mean, so one broken series cannot drag the benchmark."""
    series = [weekly(f['pts'], start, end) for f in funds if f['pts'][0][0] <= start]
    series = [s for s in series if s]
    n = min(len(s) for s in series)
    return [st.median(s[i] for s in series) for i in range(n)], len(series)


def fit(r, L, M, S):
    """Grid search the weights that minimise tracking error. Three assets and a
    sum-to-one constraint leaves two free dimensions, so an exhaustive 2% grid is
    1,326 points: no optimiser to misconfigure and no local minimum to fall into.
    A second pass at 0.5% refines around the winner."""
    n = min(len(r), len(L), len(M), len(S))
    r, L, M, S = r[:n], L[:n], M[:n], S[:n]

    def err(wl, wm, ws):
        return sum((r[t] - (wl * L[t] + wm * M[t] + ws * S[t])) ** 2 for t in range(n))

    best = min(((err(i / 50, j / 50, (50 - i - j) / 50), i / 50, j / 50, (50 - i - j) / 50)
                for i in range(51) for j in range(51 - i)))
    for _ in range(2):
        _, bl, bm, _bs = best
        step = 0.005
        cands = []
        for di in range(-4, 5):
            for dj in range(-4, 5):
                wl, wm = bl + di * step, bm + dj * step
                ws = 1 - wl - wm
                if wl < -1e-9 or wm < -1e-9 or ws < -1e-9:
                    continue
                cands.append((err(wl, wm, ws), wl, wm, ws))
        best = min(cands + [best])

    e, wl, wm, ws = best
    mu = sum(r) / n
    tss = sum((x - mu) ** 2 for x in r)
    return {'large': wl * 100, 'mid': wm * 100, 'small': ws * 100,
            'r2': (1 - e / tss) * 100 if tss else 0.0}


def window_returns(funds, start, end):
    """CAGR and worst rolling twelve months for every fund alive across the WHOLE
    window, so the comparison is like for like rather than a survivorship trick."""
    out = []
    for f in funds:
        if f['pts'][0][0] > start:
            continue
        a, b = on_or_before(f['pts'], start), on_or_before(f['pts'], end)
        if not a or not b or b[0] <= a[0]:
            continue
        days = (b[0] - a[0]).days
        cagr = ((b[1] / a[1]) ** (365.25 / days) - 1) * 100
        worst = None
        for dt, v in f['pts']:
            if dt < start or dt > end:
                continue
            back = on_or_before(f['pts'], dt - timedelta(days=365))
            if not back or back[0] < start:
                continue
            r = (v / back[1] - 1) * 100
            if worst is None or r < worst:
                worst = r
        out.append({'cagr': cagr, 'worst': worst})
    return out


# ─── main ─────────────────────────────────────────────────────────────────
def main():
    print('→ Loading NAV history')
    store = load()
    end = max(f['pts'][-1][0] for c in CATS for f in store[c])
    start = end - timedelta(days=WEEKS)
    print(f'\n  window {start:%d %b %Y} to {end:%d %b %Y}')

    L, nl = composite(store['Large Cap Fund'], start, end)
    M, nm = composite(store['Mid Cap Fund'], start, end)
    S, ns = composite(store['Small Cap Fund'], start, end)
    print(f'  benchmarks from {nl} large, {nm} mid, {ns} small cap funds, {len(L)} weeks\n')

    def fits_for(cat):
        out = []
        for f in store[cat]:
            if f['pts'][0][0] > start:
                continue
            r = weekly(f['pts'], start, end)
            if r:
                out.append(fit(r, L, M, S))
        return out

    # ── the gate ──────────────────────────────────────────────────────────
    print('  SANITY GATE: recover mandates the method should already know')
    gate = {'Large Cap Fund': ('large', 80), 'Mid Cap Fund': ('mid', 65), 'Small Cap Fund': ('small', 65)}
    fits, failed = {}, []
    for cat, (seg, floor) in gate.items():
        fits[cat] = fits_for(cat)
        med = st.median(x[seg] for x in fits[cat])
        r2 = st.median(x['r2'] for x in fits[cat])
        ok = med >= floor
        if not ok:
            failed.append(cat)
        print(f'    {cat:<16} implied {seg} {med:>5.1f}%  vs mandated {floor}%  '
              f'R2 {r2:>5.1f}%  {"PASS" if ok else "FAIL"}')
    if failed:
        sys.exit(f'\n  Gate failed for {failed}. Refusing to write cap-mix.json.')

    for cat in ('Multi Cap Fund', 'Flexi Cap Fund'):
        fits[cat] = fits_for(cat)

    # ── assemble ──────────────────────────────────────────────────────────
    out = {
        'asOf': end.strftime('%d %b %Y'),
        'window': {'from': start.strftime('%b %Y'), 'to': end.strftime('%b %Y'), 'weeks': len(L)},
        'cats': {}
    }
    for cat in CATS:
        f = fits[cat]
        rets_rule = window_returns(store[cat], datetime(2021, 2, 1), end)
        rets_3y = window_returns(store[cat], start, end)
        ms = sorted(round(x['mid'] + x['small'], 1) for x in f)
        born = sorted(x['pts'][0][0] for x in store[cat])
        # Per-column medians do not sum to 100, which leaves a gap in a stacked bar.
        # The mean does sum to 100 by construction, since every fund's own weights do,
        # so the chart uses the mean and the median is kept alongside as a robustness check.
        out['cats'][cat.replace(' Fund', '')] = {
            'n': len(f),
            'large': round(st.fmean(x['large'] for x in f), 1),
            'mid': round(st.fmean(x['mid'] for x in f), 1),
            'small': round(st.fmean(x['small'] for x in f), 1),
            'largeMed': round(st.median(x['large'] for x in f), 1),
            'midMed': round(st.median(x['mid'] for x in f), 1),
            'smallMed': round(st.median(x['small'] for x in f), 1),
            'r2': round(st.median(x['r2'] for x in f), 1),
            'midSmall': ms,
            'midSmallMed': round(st.median(ms), 1),
            'under40': sum(1 for x in ms if x < 40),
            'over60': sum(1 for x in ms if x >= 60),
            'schemes': len(store[cat]),
            'bornAfterRule': sum(1 for b in born if b > RULE_DEADLINE),
            'medianStart': born[len(born) // 2].strftime('%b %Y'),
            'ruleWindow': _stats(rets_rule),
            'w3y': _stats(rets_3y),
        }

    (ROOT / 'cap-mix.json').write_text(json.dumps(out, indent=1), encoding='utf-8')

    print(f"\n  {'':<12} {'n':>3} {'implied large/mid/small':>24} {'R2':>6} {'mid+small':>10}")
    for k, v in out['cats'].items():
        print(f"  {k:<12} {v['n']:>3} {v['large']:>8.0f} /{v['mid']:>5.0f} /{v['small']:>5.0f}"
              f"{'':>6} {v['r2']:>5.1f}% {v['midSmallMed']:>9.0f}%")
    print(f"\n  Wrote cap-mix.json  ({(ROOT / 'cap-mix.json').stat().st_size:,} bytes)")


def _stats(rows):
    if not rows:
        return None
    cg = sorted(r['cagr'] for r in rows)
    w = [r['worst'] for r in rows if r['worst'] is not None]
    return {'n': len(cg), 'med': round(st.median(cg), 1),
            'lo': round(cg[0], 1), 'hi': round(cg[-1], 1),
            'worstMed': round(st.median(w), 1) if w else None,
            'worstMin': round(min(w), 1) if w else None}


if __name__ == '__main__':
    main()
