"""Category Compass: which equity fund category does the data lean towards today?

Scores seven SEBI equity categories on three tests, each 0 to 100:
  Valuation  is it cheap compared with its own past?           (P/B, P/E, and price vs large caps)
  Momentum   is it already rising?                             (40-week average, 6 and 12 month returns vs market)
  Risk       is it calm?                                       (6 month volatility vs its own past, India VIX)

Each category is tracked through the NSE index its funds actually fish in, because an
index has clean daily P/E and P/B going back to 2016 and a fund NAV mixes in one
manager's skill. Every percentile is computed only from weeks up to that point
(expanding window), so the backtest at the end never sees the future.

Sources: NSE ind_close_all_DDMMYYYY.csv, the same archive Market Pulse reads.
History lives in content/category-compass/weekly.csv; each run fetches only the
weeks after its last row, so a build adds a few requests, not five hundred.
If NSE is down the old category-compass.json stays, with its old date on it.

Run:  python3 build/category_compass.py
"""
import bisect, csv, io, json, math, statistics, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / 'content' / 'category-compass' / 'weekly.csv'
OUT = ROOT / 'category-compass.json'
URL = 'https://nsearchives.nseindia.com/content/indices/ind_close_all_{:%d%m%Y}.csv'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Referer': 'https://www.nseindia.com/'}

# SEBI category -> the NSE index whose stocks those funds are allowed to buy.
CATEGORIES = [
    {'key': 'large',    'name': 'Large cap',       'index': 'Nifty 100',
     'what': "India's 100 biggest companies"},
    {'key': 'largemid', 'name': 'Large and mid cap', 'index': 'NIFTY LargeMidcap 250',
     'what': 'At least 35% large and 35% mid cap'},
    {'key': 'flexi',    'name': 'Flexi cap',       'index': 'Nifty 500',
     'what': 'Manager free to pick any size'},
    {'key': 'multi',    'name': 'Multi cap',       'index': 'Nifty500 Multicap 50:25:25',
     'what': 'At least 25% each in large, mid and small'},
    {'key': 'mid',      'name': 'Mid cap',         'index': 'Nifty Midcap 150',
     'what': 'Companies ranked 101 to 250 by size'},
    {'key': 'small',    'name': 'Small cap',       'index': 'Nifty Smallcap 250',
     'what': 'Companies ranked 251 and below'},
    {'key': 'value',    'name': 'Value and contra', 'index': 'NIFTY500 Value 50',
     'what': 'Stocks cheap on earnings, book value and dividends'},
]
BENCH, LARGE, VIX = 'Nifty 500', 'Nifty 100', 'India VIX'
WANTED = {c['index'].lower() for c in CATEGORIES} | {VIX.lower()}

WEIGHTS = {'valuation': 0.40, 'momentum': 0.35, 'risk': 0.25}
PE_COMPARABLE_FROM = date(2021, 4, 1)  # NSE moved index P/E to consolidated earnings
PE_SANE_MAX = 80             # above this, loss-making companies are distorting the index P/E
MIN_HISTORY_WEEKS = 104      # two years before a percentile is allowed to mean anything
MA_WEEKS = 40                # about 200 trading days


# ─── Data ─────────────────────────────────────────────────────────────────
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _get(day):
    req = urllib.request.Request(URL.format(day), headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(2 ** attempt)
    return None


def _week_rows(friday):
    """Rows for the last trading day of the week ending on this Friday."""
    for back in range(5):
        day = friday - timedelta(days=back)
        if day > date.today():
            continue
        text = _get(day)
        if not text:
            continue
        rows = [[day.isoformat(), r['Index Name'].strip(), _num(r.get('Closing Index Value')),
                 _num(r.get('P/E')), _num(r.get('P/B')), _num(r.get('Div Yield'))]
                for r in csv.DictReader(io.StringIO(text))
                if (r.get('Index Name') or '').strip().lower() in WANTED]
        if rows:
            return rows
    return []


def refresh_history():
    """Append the weeks after the last stored row. Re-fetch the last stored week
    too, because a mid-week run stores a Wednesday that should become a Friday."""
    rows = list(csv.reader(HISTORY.open()))[1:] if HISTORY.exists() else []
    last = date.fromisoformat(max(r[0] for r in rows)) if rows else date(2016, 4, 1)
    friday = last + timedelta(days=(4 - last.weekday()) % 7)
    fridays = []
    while friday - timedelta(days=4) <= date.today():
        fridays.append(friday)
        friday += timedelta(days=7)
    with ThreadPoolExecutor(max_workers=6) as ex:
        fresh = [r for wk in ex.map(_week_rows, fridays) for r in wk]
    if not fresh:
        print(f'  No new NSE data after {last}; keeping history as is')
        return
    weeks_fresh = {date.fromisoformat(r[0]) - timedelta(days=date.fromisoformat(r[0]).weekday()) for r in fresh}
    keep = [r for r in rows
            if date.fromisoformat(r[0]) - timedelta(days=date.fromisoformat(r[0]).weekday()) not in weeks_fresh]
    allrows = sorted(keep + [[str(x) if x is not None else '' for x in r] for r in fresh])
    with HISTORY.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['date', 'index', 'close', 'pe', 'pb', 'dy'])
        w.writerows(allrows)
    print(f'  Added {len(weeks_fresh)} week(s) of NSE data, latest {max(r[0] for r in fresh)}')


def load():
    """One row per week, labelled with the real last trading day of that week.
    Returns (dates, {index: {'close': [...], 'pe': [...], 'pb': [...]}}) with None for gaps."""
    by_week = {}
    with HISTORY.open() as f:
        for r in csv.DictReader(f):
            d = date.fromisoformat(r['date'])
            wk = d + timedelta(days=(4 - d.weekday()) % 7)
            slot = by_week.setdefault(wk, {'day': d, 'rows': {}})
            slot['day'] = max(slot['day'], d)
            prev = slot['rows'].get(r['index'])
            if prev is None or prev[0] <= d:
                slot['rows'][r['index']] = (d, _num(r['close']), _num(r['pe']), _num(r['pb']))
    weeks = sorted(by_week)
    dates = [by_week[w]['day'] for w in weeks]
    names = {n for w in weeks for n in by_week[w]['rows']}
    data = {}
    for n in names:
        rows = [by_week[w]['rows'].get(n) for w in weeks]
        data[n] = {f: [r[i] if r else None for r in rows] for f, i in (('close', 1), ('pe', 2), ('pb', 3))}
    return dates, data


# ─── Small series helpers (lists aligned to weeks, None = no value) ───────
def ok(*xs):
    return all(x is not None and not (isinstance(x, float) and math.isnan(x)) for x in xs)


def expanding_pct(s, min_periods=MIN_HISTORY_WEEKS):
    """Share of weeks so far with a lower value than this week, 0 to 100."""
    seen, out = [], []
    for v in s:
        if not ok(v):
            out.append(None)
            continue
        bisect.insort(seen, v)
        out.append(100.0 * bisect.bisect_left(seen, v) / len(seen) if len(seen) >= min_periods else None)
    return out


def change(s, n):
    return [s[i] / s[i - n] - 1 if i >= n and ok(s[i], s[i - n]) else None for i in range(len(s))]


def lead(s, n):
    return [s[i + n] if i + n < len(s) else None for i in range(len(s))]


def rolling(s, n, min_n, fn):
    out = []
    for i in range(len(s)):
        win = [x for x in s[max(0, i - n + 1):i + 1] if ok(x)]
        out.append(fn(win) if len(win) >= min_n else None)
    return out


def mean_of(*cols):
    out = []
    for xs in zip(*cols):
        xs = [x for x in xs if ok(x)]
        out.append(sum(xs) / len(xs) if xs else None)
    return out


def ratio(a, b):
    return [x / y if ok(x, y) and y else None for x, y in zip(a, b)]


def median(xs):
    xs = [x for x in xs if ok(x)]
    return statistics.median(xs) if xs else None


# ─── Model ────────────────────────────────────────────────────────────────
def score(dates, data):
    vix_pct = expanding_pct(data[VIX]['close'])
    bench = data[BENCH]['close']
    b26, b52 = change(bench, 26), change(bench, 52)
    n = len(dates)
    parts = {}
    for c in CATEGORIES:
        ix = c['index']
        close, pe, pb = data[ix]['close'], data[ix]['pe'], data[ix]['pb']
        p = {'close': close, 'pe': pe, 'pb': pb}

        # Valuation: cheap scores high, so the score is 100 minus the percentile.
        pb_pct = expanding_pct(pb)
        pe_clean = [v if ok(v) and 0 < v < PE_SANE_MAX and d >= PE_COMPARABLE_FROM else None
                    for v, d in zip(pe, dates)]
        pe_pct = expanding_pct(pe_clean, min_periods=52)
        own = mean_of(pb_pct, pe_pct)
        if ix == LARGE:
            # Large caps look relatively cheap when mid and small trade at a big premium to them.
            rels = [expanding_pct(ratio(data[o]['pb'], pb)) for o in ('Nifty Midcap 150', 'Nifty Smallcap 250')]
            rel = [100 - x if ok(x) else None for x in mean_of(*rels)]
        else:
            rel = expanding_pct(ratio(pb, data[LARGE]['pb']))
        p.update(pb_pct=pb_pct, pe_pct=pe_pct, rel_pct=rel)
        p['valuation'] = [100 - x if ok(x) else None for x in mean_of(own, rel)]

        # Momentum: above its 40-week average, and beating the whole market over 6 and 12 months.
        ma = rolling(close, MA_WEEKS, MA_WEEKS, lambda w: sum(w) / len(w))
        above = [(1.0 if ok(x) and x > m else 0.0) if ok(m) else None for x, m in zip(close, ma)]
        r26, r52 = change(close, 26), change(close, 52)
        if ix == BENCH:
            rel_ret = [(a + b) / 2 if ok(a, b) else None for a, b in zip(r26, r52)]  # the market cannot beat itself
        else:
            rel_ret = [((a - x) + (b - y)) / 2 if ok(a, b, x, y) else None for a, b, x, y in zip(r26, r52, b26, b52)]
        mom_pct = expanding_pct(rel_ret, min_periods=52)
        p.update(above_ma=above, ret_6m=r26, ret_12m=r52)
        p['momentum'] = [50 * a + 0.5 * m if ok(a, m) else None for a, m in zip(above, mom_pct)]

        # Risk: calmer than its own past scores high. Market-wide fear (VIX) counts too.
        weekly = change(close, 1)
        vol = rolling(weekly, 26, 20, lambda w: statistics.stdev(w) * math.sqrt(52))
        hi52 = rolling(close, 52, 26, max)
        p['vol'] = vol
        p['drawdown'] = [x / h - 1 if ok(x, h) else None for x, h in zip(close, hi52)]
        vol_pct = expanding_pct(vol, min_periods=52)
        p['risk'] = [100 - (0.6 * v + 0.4 * x) if ok(v, x) else None for v, x in zip(vol_pct, vix_pct)]

        p['score'] = [sum(WEIGHTS[k] * p[k][i] for k in WEIGHTS) if ok(*(p[k][i] for k in WEIGHTS)) else None
                      for i in range(n)]
        f52, f156 = lead(close, 52), lead(close, 156)
        p['fwd_1y'] = [f / x - 1 if ok(f, x) else None for f, x in zip(f52, close)]
        p['fwd_3y'] = [(f / x) ** (1 / 3) - 1 if ok(f, x) else None for f, x in zip(f156, close)]
        parts[c['key']] = p
    return parts


def backtest(dates, parts):
    """Replay the score every week and check what happened next."""
    groups = {'away': [], 'neutral': [], 'towards': []}
    for p in parts.values():
        for s, f1, f3 in zip(p['score'], p['fwd_1y'], p['fwd_3y']):
            if ok(s):
                groups['towards' if s >= 60 else 'away' if s < 40 else 'neutral'].append((f1, f3))
    buckets = []
    for b in ('away', 'neutral', 'towards'):
        g = groups[b]
        f1 = [x for x, _ in g if ok(x)]
        buckets.append({'bucket': b, 'weeks': len(g),
                        'fwd_1y_median': _f(median(f1)),
                        'fwd_1y_hit': _f(sum(x > 0 for x in f1) / len(f1) if f1 else None),
                        'fwd_3y_median': _f(median([y for _, y in g]))})

    # Each week hold whichever of large / mid / small scored highest last week,
    # against a fixed one-third in each.
    keys = ['large', 'mid', 'small']
    rets = {k: change(parts[k]['close'], 1) for k in keys}
    days, strat, equal, legs = [], [], [], {k: [] for k in keys}
    picks = []
    for i in range(1, len(dates)):
        prev = {k: parts[k]['score'][i - 1] for k in keys}
        now = {k: rets[k][i] for k in keys}
        if not ok(*prev.values()) or not ok(*now.values()):
            continue
        pick = max(keys, key=lambda k: prev[k])
        picks.append(pick)
        days.append(dates[i])
        strat.append(now[pick])
        equal.append(sum(now.values()) / 3)
        for k in keys:
            legs[k].append(now[k])

    def path(r):
        w, out = 1.0, []
        for x in r:
            w *= 1 + x
            out.append(w)
        return out

    def cagr(r): return path(r)[-1] ** (52 / len(r)) - 1

    def mdd(r):
        peak, worst = 1.0, 0.0
        for w in path(r):
            peak = max(peak, w)
            worst = min(worst, w / peak - 1)
        return worst

    curves = {'rotation': path(strat), 'equal': path(equal), **{k: path(legs[k]) for k in keys}}
    return {
        'buckets': buckets,
        'rotation': {
            'from': days[0].isoformat(), 'to': days[-1].isoformat(),
            'cagr_rotation': _f(cagr(strat)), 'cagr_equal': _f(cagr(equal)),
            **{f'cagr_{k}': _f(cagr(legs[k])) for k in keys},
            'mdd_rotation': _f(mdd(strat)), 'mdd_equal': _f(mdd(equal)),
            **{f'mdd_{k}': _f(mdd(legs[k])) for k in keys},
            'switches': sum(a != b for a, b in zip(picks, picks[1:])),
            'growth': [{'d': days[i].isoformat(), **{c: round(curves[c][i], 4) for c in curves}}
                       for i in range(0, len(days), 2)],
        },
    }


def _f(x, nd=4):
    return round(float(x), nd) if ok(x) else None


def build():
    dates, data = load()
    parts = score(dates, data)
    last = max(i for i, v in enumerate(data[BENCH]['close']) if ok(v))
    asof = dates[last]
    cats = []
    for c in CATEGORIES:
        p = parts[c['key']]
        i = max(j for j in range(last + 1) if ok(p['close'][j]))
        first = min(j for j, v in enumerate(p['pb']) if ok(v))
        cats.append({
            **c,
            'history_from': dates[first].isoformat(),
            'score': _f(p['score'][i], 1),
            **{k: _f(p[k][i], 1) for k in ('valuation', 'momentum', 'risk')},
            'pb': _f(p['pb'][i], 2), 'pe': _f(p['pe'][i], 2), 'pb_median': _f(median(p['pb']), 2),
            **{k: _f(p[k][i], 0) for k in ('pb_pct', 'pe_pct', 'rel_pct')},
            'above_ma': p['above_ma'][i] == 1,
            **{k: _f(p[k][i]) for k in ('ret_6m', 'ret_12m', 'vol', 'drawdown')},
            'series': [{'d': dates[j].isoformat(), 'pb': _f(p['pb'][j], 2)}
                       for j in [j for j in range(len(dates)) if ok(p['pb'][j])][::2]],
        })
    vix = data[VIX]['close']
    vix_pct = expanding_pct(vix)
    out = {
        'asof': asof.isoformat(),
        'weights': WEIGHTS,
        'vix': _f(vix[last], 2),
        'vix_pct': _f(vix_pct[last], 0),
        'categories': cats,
        'backtest': backtest(dates, parts),
    }
    OUT.write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    top = max(cats, key=lambda c: c['score'])
    print(f'  Category Compass as of {out["asof"]}: leans to {top["name"]} ({top["score"]})')


def main():
    try:
        refresh_history()
    except Exception as e:
        print(f'  NSE refresh skipped ({e}); scoring the history already stored')
    build()


if __name__ == '__main__':
    main()
