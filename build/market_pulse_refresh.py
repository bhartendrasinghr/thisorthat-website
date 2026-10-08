"""Refresh the computable half of content/market-pulse.json.

The rule this script obeys: it only ever writes numbers it derived itself, and
it never touches a word anybody wrote. Editorial fields, the behaviour gap, the
two First Global charts and every manually sourced tile are read and written
back untouched. If a source is down, the previous value stays and the stamp
stays old, which is the honest failure: a stale number that says it is stale.

Sources, all free and official:
  NSE  ind_close_all_DDMMYYYY.csv   every index, plus P/E, P/B, dividend yield
  NSE  BhavCopy ... .csv.zip        every stock, for breadth
  NSE  corporate actions API        so a bonus is not counted as a fall
  open.er-api.com                   USD/INR

Run:  python3 build/market_pulse_refresh.py
"""
import csv, io, json, os, re, sys, urllib.request, zipfile
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'content', 'market-pulse.json')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Referer': 'https://www.nseindia.com/'}


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


# ─── NSE index archive ────────────────────────────────────────────────────
def indices(d):
    """Every NSE index for one date, or None if it was not a trading day."""
    try:
        raw = get(f'https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv')
    except Exception:
        return None
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8', 'replace'))))
    out = {}
    for r in rows:
        name = (r.get('Index Name') or '').strip()
        if not name:
            continue
        def num(k):
            try: return float((r.get(k) or '').strip())
            except ValueError: return None
        out[name] = {'close': num('Closing Index Value'), 'chg': num('Change(%)'),
                     'pe': num('P/E'), 'pb': num('P/B'), 'dy': num('Div Yield')}
    return out or None


def walk_back(start, fn, limit=12):
    """Markets close for holidays. Step back a day at a time until data appears."""
    d = start
    for _ in range(limit):
        got = fn(d)
        if got:
            return d, got
        d -= timedelta(days=1)
    return None, None


def walk_fwd(start, fn, limit=12):
    d = start
    for _ in range(limit):
        got = fn(d)
        if got:
            return d, got
        d += timedelta(days=1)
    return None, None


# ─── NSE bhavcopy, for breadth ────────────────────────────────────────────
def bhav(d):
    """Closing price per company (EQ series, INE ISINs) for one date."""
    if d >= date(2024, 1, 1):
        url = f'https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip'
    else:
        mon = f'{d:%b}'.upper()
        url = (f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{mon}/'
               f'cm{d:%d}{mon}{d:%Y}bhav.csv.zip')
    try:
        z = zipfile.ZipFile(io.BytesIO(get(url)))
    except Exception:
        return None
    name = [n for n in z.namelist() if n.lower().endswith('.csv')]
    if not name:
        return None
    rows = list(csv.DictReader(io.StringIO(z.read(name[0]).decode('utf-8', 'replace'))))
    out = {}
    for r in rows:
        if 'TckrSymb' in r:
            isin, srs, close = (r.get('ISIN') or '').strip(), (r.get('SctySrs') or '').strip(), r.get('ClsPric')
        else:
            isin, srs, close = (r.get('ISIN') or '').strip(), (r.get('SERIES') or '').strip(), r.get('CLOSE')
        if srs != 'EQ' or not isin.startswith('INE'):
            continue
        try: c = float(close)
        except (TypeError, ValueError): continue
        if c > 0:
            out[isin] = c
    return out or None


def splits_since(start):
    """Split and bonus factors since `start`, so a bonus is not read as a crash."""
    fac = {}
    d = start.replace(day=1)
    while d <= date.today():
        nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        try:
            raw = get('https://www.nseindia.com/api/corporates-corporateActions?index=equities'
                      f'&from_date={d:%d-%m-%Y}&to_date={min(nxt, date.today()):%d-%m-%Y}', timeout=45)
            data = json.loads(raw)
        except Exception:
            d = nxt; continue
        for r in (data if isinstance(data, list) else data.get('data', [])):
            isin, subj, ex = (r.get('isin') or '').strip(), r.get('subject') or '', (r.get('exDate') or '').strip()
            if not isin or not ex:
                continue
            f = None
            m = re.search(r'bonus\s+(\d+)\s*:\s*(\d+)', subj, re.I)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if a + b: f = b / (a + b)
            if f is None:
                m = re.search(r'from\s+rs?\.?\s*([\d.]+)\s*(?:/-)?\s*to\s+rs?\.?\s*([\d.]+)', subj, re.I)
                if m:
                    fr, to = float(m.group(1)), float(m.group(2))
                    if fr > 0 and 0 < to < fr: f = to / fr
            if f and 0 < f < 1:
                fac[isin] = fac.get(isin, 1.0) * f
        d = nxt
    return fac


def usdinr():
    try:
        d = json.loads(get('https://open.er-api.com/v6/latest/USD', timeout=30))
        return d['rates']['INR'] if d.get('result') == 'success' else None
    except Exception:
        return None


# ─── main ─────────────────────────────────────────────────────────────────
def main():
    doc = json.load(open(TARGET, encoding='utf-8'))
    today = date.today()
    jan1 = date(today.year, 1, 1)

    print('→ NSE index archive')
    end_d, end_i = walk_back(today, indices)
    start_d, start_i = walk_fwd(jan1, indices)
    if not (end_i and start_i):
        sys.exit('  could not reach the NSE index archive; nothing written')
    print(f'  {start_d} to {end_d}')

    stamp = end_d.isoformat()
    auto = {}

    n50 = 'Nifty 50'
    if n50 in end_i and n50 in start_i and start_i[n50]['close']:
        ytd = (end_i[n50]['close'] / start_i[n50]['close'] - 1) * 100
        auto['nifty_ytd'] = {'v': f'{ytd:+.1f}%'.replace('-', '\u2212'),
                             'sub': f'Nifty 50, {start_d:%-d %b} to {end_d:%-d %b}', 'raw': round(ytd, 2)}
        print(f'  Nifty 50 YTD {ytd:+.1f}%')
    if end_i.get(n50, {}).get('pe'):
        auto['nifty_pe'] = {'v': f"{end_i[n50]['pe']:.1f}",
                            'sub': f"P/B {end_i[n50]['pb']:.2f} · yield {end_i[n50]['dy']:.2f}%",
                            'raw': end_i[n50]['pe']}
        print(f"  Nifty 50 P/E {end_i[n50]['pe']}")

    sect = [v['chg'] for k, v in end_i.items() if k.startswith('Nifty') and v['chg'] is not None]
    if sect:
        pctup = 100 * sum(1 for c in sect if c > 0) / len(sect)
        auto['sectors_up'] = {'v': f'{pctup:.0f}%', 'sub': f'of {len(sect)} NSE indices, on {end_d:%-d %b}',
                              'raw': round(pctup, 1)}
        print(f'  indices up on the day: {pctup:.0f}% of {len(sect)}')

    print('→ NSE bhavcopy, for breadth')
    _, b_end = walk_back(end_d, bhav)
    _, b_start = walk_fwd(jan1, bhav)
    if b_end and b_start:
        print('→ corporate actions, so a bonus is not read as a fall')
        adj = splits_since(jan1)
        both = [k for k in b_start if k in b_end]
        up = sum(1 for k in both if b_end[k] > b_start[k] * adj.get(k, 1.0))
        pctup = 100 * up / len(both)
        auto['stocks_up'] = {'v': f'{pctup:.0f}%',
                             'sub': f'of {len(both):,} NSE companies, split adjusted',
                             'raw': round(pctup, 1)}
        print(f'  {up:,} of {len(both):,} up ({pctup:.0f}%), {len(adj)} companies restated')

    print('→ USD/INR')
    fx = usdinr()
    if fx:
        # The free FX feed gives today only, so the year-open rate is a once-a-year
        # human input held in fx_year_open. With it we can show the move, which is
        # what matters; without it we show the level, which is at least true.
        opn = doc.get('fx_year_open')
        if opn:
            mv = (opn / fx - 1) * 100          # rupee's own change, not the pair's
            auto['usdinr'] = {'v': f'{mv:+.1f}%'.replace('-', '\u2212'),
                              'sub': f'\u20b9{fx:.2f} per dollar, from \u20b9{opn:.2f} on 1 Jan',
                              'raw': round(mv, 2)}
            print(f'  {fx:.2f}, rupee {mv:+.1f}% this year')
        else:
            auto['usdinr'] = {'v': f'\u20b9{fx:.2f}', 'sub': 'per dollar. Set fx_year_open to show the move.',
                              'raw': round(fx, 4)}
            print(f'  {fx:.2f} (no fx_year_open set, showing the level)')

    # Write back: only fields explicitly marked auto, matched by their key.
    MAP = {'Nifty 50': 'nifty_ytd', 'Stocks up YTD': 'stocks_up',
           'Indices up on the day': 'sectors_up', 'Rupee per dollar': 'usdinr',
           'Nifty 50 P/E': 'nifty_pe'}
    touched = 0
    for tile in doc.get('scoreboard', []):
        key = MAP.get(tile.get('k'))
        if key and key in auto and tile.get('auto'):
            tile['v'] = auto[key]['v']; tile['sub'] = auto[key]['sub']; tile['asof'] = stamp
            touched += 1
    for g in doc.get('tracker_groups', []):
        for c in g.get('cards', []):
            key = MAP.get(c.get('k'))
            if key and key in auto and c.get('auto'):
                c['v'] = auto[key]['v']; c['sub'] = auto[key]['sub']; c['asof'] = stamp
                touched += 1

    doc['auto_refreshed'] = stamp
    json.dump(doc, open(TARGET, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'\n  updated {touched} auto fields, stamped {stamp}')
    print('  every editorial field left exactly as written')


if __name__ == '__main__':
    main()
