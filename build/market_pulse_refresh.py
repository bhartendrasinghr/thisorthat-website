"""Refresh the computable half of content/market-pulse.json.

The rule this script obeys: it only ever writes numbers it derived itself, and
it never touches a word anybody wrote. Editorial fields, the behaviour gap, the
two First Global charts and every manually sourced tile are read and written
back untouched. If a source is down, the previous value stays and the stamp
stays old, which is the honest failure: a stale number that says it is stale.

Sources, all free and public:
  NSE  ind_close_all_DDMMYYYY.csv   every index, plus P/E, P/B, dividend yield
  NSE  BhavCopy ... .csv.zip        every stock, for breadth
  NSE  corporate actions API        so a bonus is not counted as a fall
  open.er-api.com                   USD/INR
  FRED fredgraph.csv                S&P 500, US 10-year Treasury
  Yahoo chart API                   gold, Brent, the dollar index
  worldgovernmentbonds.com          India's 10-year G-sec, and its 1 January level

Two figures are deliberately NOT automated, because no source we can rely on
publishes them in a machine readable form: the RBI repo rate and stance, which
moves only at an MPC meeting, and CPI, which MoSPI puts out as a press release
around the 12th. Rather than let those rot quietly, the build prints what is
overdue and writes the same list to content/market-pulse-review.json. The
licensed charts, the behaviour gap and every word of the prose are the same:
a person's job, and the review list says so.

Run:  python3 build/market_pulse_refresh.py
"""
import csv, io, json, os, re, sys, urllib.request, zipfile
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'content', 'market-pulse.json')
REVIEW = os.path.join(ROOT, 'content', 'market-pulse-review.json')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
      'Referer': 'https://www.nseindia.com/'}

# FRED sits behind a CDN that tarpits a browser User-Agent arriving without a
# browser's TLS fingerprint: the request hangs until it times out, with no
# error to read. A plain client string is served in under a second. Found the
# hard way, so do not "tidy" these two dictionaries into one.
PLAIN = {'User-Agent': 'curl/8.7.1', 'Accept': '*/*'}


def get(url, timeout=60, headers=None):
    req = urllib.request.Request(url, headers=headers or UA)
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


# ─── the world outside India ──────────────────────────────────────────────
def fred(series):
    """Daily observations from FRED, as [(iso date, value)], oldest first."""
    url = (f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'
           f'&cosd={date.today().year - 1}-11-01&coed={date.today():%Y-%m-%d}')
    try:
        raw = get(url, timeout=45, headers=PLAIN).decode('utf-8', 'replace')
    except Exception:
        return None
    rows = []
    for line in raw.strip().splitlines()[1:]:
        cell = line.split(',')
        if len(cell) < 2:
            continue
        try:
            rows.append((cell[0].strip(), float(cell[1])))
        except ValueError:
            continue                      # FRED writes '.' on a holiday
    return rows or None


def treasury10():
    """The US 10-year, from the Treasury's own daily yield curve.

    Preferred over FRED for this one figure because it is the issuer's own
    published curve and it carries the current day, where FRED runs a day
    behind. The file is the whole calendar year, newest row first, so it
    holds both the January level and today's in one request.
    """
    url = ('https://home.treasury.gov/resource-center/data-chart-center/'
           'interest-rates/daily-treasury-rates.csv/{y}/all'
           '?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv')
    try:
        raw = get(url.format(y=date.today().year), timeout=45).decode('utf-8', 'replace')
    except Exception:
        return None
    rows = []
    for r in csv.DictReader(io.StringIO(raw)):
        try:
            d = datetime.strptime(r['Date'].strip(), '%m/%d/%Y').date()
            rows.append((d.isoformat(), float(r['10 Yr'])))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    if len(rows) < 2:
        return None
    rows.sort()                                   # the file arrives newest first
    (bd, bv), (ld, lv) = rows[0], rows[-1]
    return {'base_date': bd, 'base': bv, 'date': ld, 'last': lv,
            'pct': (lv / bv - 1) * 100, 'bps': (lv - bv) * 100}


def goldspot():
    """Gold in dollars an ounce, right now.

    Nobody publishes a free daily gold history we can rely on from a build
    box: FRED retired its LBMA fixing series, and the exchanges want a key.
    So this reads the live price only, and the 1 January level is a once-a-year
    human input held in gold_year_open, exactly as the rupee's is. The review
    list nags for both every January.
    """
    try:
        d = json.loads(get('https://api.gold-api.com/price/XAU', timeout=30))
        return float(d['price'])
    except Exception:
        return None


def ytd(rows, year):
    """Year to date, measured against the last close of the previous year."""
    if not rows:
        return None
    before = [r for r in rows if r[0] < f'{year}-01-01']
    if not before or not before[-1][1] or not rows[-1][1]:
        return None
    (bd, bv), (ld, lv) = before[-1], rows[-1]
    return {'base_date': bd, 'base': bv, 'date': ld, 'last': lv,
            'pct': (lv / bv - 1) * 100, 'bps': (lv - bv) * 100}


def sane(v, lo, hi):
    """A number we are willing to publish. Anything else is a parse gone wrong."""
    return v is not None and lo <= v <= hi


def minus(s):
    """The page uses a real minus sign, not a hyphen, for every negative."""
    return s.replace('-', '−')


def nice(iso):
    return datetime.strptime(iso, '%Y-%m-%d').strftime('%-d %b')


def pctnum(s):
    """The first percentage in a string like '5.50%' or '−0.04%'."""
    m = re.search(r'(−|-)?\s*([\d.]+)\s*%', str(s or ''))
    if not m:
        return None
    return -float(m.group(2)) if m.group(1) else float(m.group(2))


def card(doc, key):
    for g in doc.get('tracker_groups', []):
        for c in g.get('cards', []):
            if c.get('k') == key:
                return c
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
        nifty_pct = (end_i[n50]['close'] / start_i[n50]['close'] - 1) * 100
        auto['nifty_ytd'] = {'v': f'{nifty_pct:+.1f}%'.replace('-', '\u2212'),
                             'sub': f'Nifty 50, {start_d:%-d %b} to {end_d:%-d %b}',
                             'raw': round(nifty_pct, 2)}
        print(f'  Nifty 50 YTD {nifty_pct:+.1f}%')
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

    # ─── the world outside India ──────────────────────────────────────────
    # Everything in this block used to be typed in by hand once a month off a
    # licensed PDF, which is why it was always a month stale. The sources are
    # daily and public, so the page can carry them stamped instead. Each is
    # bounds checked: an implausible number is refused, and a refusal leaves
    # the old figure and its old date exactly where they were.
    print('→ the world outside India')
    yr = today.year
    mkt = {}
    # FRED for the three it publishes as a clean daily series. Note which
    # Brent and which dollar these are: the spot price the EIA quotes, not the
    # front month, and the Fed's broad trade-weighted basket, not the DXY six.
    # Both subs say so on the page, because a reader who checks against a
    # market site will otherwise think the page is wrong.
    for key, label, series, lo, hi in [
            ('spx',   'S&P 500',            'SP500',        -60, 60),
            ('brent', 'Brent, spot',        'DCOILBRENTEU', -90, 300),
            ('dxy',   'broad dollar index', 'DTWEXBGS',     -30, 30)]:
        r = ytd(fred(series), yr)
        if r and sane(r['pct'], lo, hi):
            mkt[key] = r
            print(f"  {label} {r['pct']:+.1f}% YTD, as of {r['date']}")
        else:
            print(f'  {label}: no usable figure, leaving the one that is there')

    print('→ gold')
    g_now, g_open = goldspot(), doc.get('gold_year_open')
    if sane(g_now, 200, 20000) and sane(g_open, 200, 20000):
        p = (g_now / g_open - 1) * 100
        if sane(p, -60, 60):
            mkt['gold'] = {'pct': p, 'last': g_now, 'base': g_open,
                           'date': today.isoformat()}
            print(f'  ${g_now:,.0f} an ounce, {p:+.1f}% from ${g_open:,.0f} on 1 Jan')
    if 'gold' not in mkt:
        print('  no usable figure, leaving the one that is there')

    if 'brent' in mkt:
        b = mkt['brent']
        auto['brent'] = {'v': minus(f"{b['pct']:+.0f}%"), 'raw': round(b['pct'], 2),
                         'sub': f"Brent spot, 1 Jan to {nice(b['date'])}", 'asof': b['date']}
        auto['brent_card'] = {'v': minus(f"{b['pct']:+.1f}%"), 'raw': round(b['pct'], 2),
                              'sub': 'YTD, USD, spot', 'asof': b['date'],
                              'src': 'FRED, EIA series', 'freq': 'Daily'}
    if 'dxy' in mkt:
        x = mkt['dxy']
        auto['dxy'] = {'v': minus(f"{x['pct']:+.1f}%"), 'raw': round(x['pct'], 2),
                       'sub': f"Fed broad index, YTD to {nice(x['date'])}", 'asof': x['date'],
                       'src': 'FRED', 'freq': 'Daily'}

    print('→ US 10-year Treasury')
    ust = treasury10() or ytd(fred('DGS10'), yr)
    if ust and sane(ust['last'], 0, 12) and sane(ust['bps'], -400, 400):
        auto['ust10'] = {'v': f"{ust['last']:.2f}%", 'raw': ust['last'],
                         'sub': minus(f"{ust['bps']:+.0f} bps YTD"), 'asof': ust['date'],
                         'src': 'US Treasury', 'freq': 'Daily'}
        print(f"  {ust['last']:.2f}%, {ust['bps']:+.0f} bps YTD, as of {ust['date']}")
    else:
        print('  no usable figure, leaving the one that is there')

    # The two tiles that answer "what would this have done to my money".
    # Compounded, not added: a 7.8% market and a 5.0% currency make 13.1%,
    # not 12.8%, and at these sizes that gap is visible.
    opn = doc.get('fx_year_open')
    if fx and opn:
        dollar, rupee = fx / opn, (opn / fx - 1) * 100
        for key, src, label in [('spx', 'spx_inr', 'S&P 500'), ('gold', 'gold_inr', 'gold')]:
            if key not in mkt:
                continue
            p = ((1 + mkt[key]['pct'] / 100) * dollar - 1) * 100
            auto[src] = {
                'v': minus(f'{p:+.1f}%'), 'raw': round(p, 2),
                'sub': minus(f"{mkt[key]['pct']:+.1f}% in dollars, rupee {rupee:+.1f}%"),
                'asof': mkt[key]['date'], 'tone': 'up' if p >= 0 else 'down'}
            print(f'  {label} in rupees {p:+.1f}%')

    # Repo minus CPI. Both inputs are hand-entered, so this is the one derived
    # figure whose date belongs to its slowest input, not to today.
    repo_c, cpi_c = card(doc, 'RBI repo rate'), card(doc, 'CPI inflation')
    repo, cpi = pctnum((repo_c or {}).get('v')), pctnum((cpi_c or {}).get('v'))
    if repo is not None and cpi is not None:
        r = repo - cpi
        auto['real_rate'] = {'v': minus(f'{r:+.2f}%'), 'raw': round(r, 2),
                             'sub': 'Repo minus CPI', 'src': 'Derived',
                             'asof': (cpi_c or {}).get('asof') or stamp}
        print(f'→ real interest rate {r:+.2f}% ({repo:.2f}% repo minus {cpi:.2f}% CPI)')

    # Write back: only fields explicitly marked auto, matched by their key.
    MAP = {'Nifty 50': 'nifty_ytd', 'Stocks up YTD': 'stocks_up',
           'Indices up on the day': 'sectors_up', 'Rupee per dollar': 'usdinr',
           'Nifty 50 P/E': 'nifty_pe',
           # automated November 2026; until then these were typed in monthly
           'S&P 500 in ₹': 'spx_inr', 'Gold in ₹': 'gold_inr',
           'Crude (energy)': 'brent',
           'Crude oil (energy)': 'brent_card', 'USD/INR': 'usdinr',
           'US 10-year yield': 'ust10',
           'Dollar index': 'dxy', 'Real interest rate': 'real_rate'}
    touched, written = 0, []

    def put(node):
        """Write one field, if it is marked auto and we have a figure for it."""
        nonlocal touched
        key = MAP.get(node.get('k'))
        if not (key and key in auto and node.get('auto')):
            return
        src = auto[key]
        node['v'], node['sub'] = src['v'], src['sub']
        node['asof'] = src.get('asof', stamp)
        for carry in ('tone', 'src', 'freq'):
            if src.get(carry):
                node[carry] = src[carry]
        written.append(node['asof'])
        touched += 1

    for tile in doc.get('scoreboard', []):
        put(tile)
    for g in doc.get('tracker_groups', []):
        for c in g.get('cards', []):
            put(c)

    # When the robot last managed to run, which is the one thing this field is
    # for: the SOP tells a reader to check it, and an old date here means the
    # nightly job is failing. How current each individual figure is belongs to
    # that figure's own stamp, because the sources publish at different hours.
    doc['auto_refreshed'] = today.isoformat()
    oldest = min(written) if written else stamp

    # ─── what still needs a person ────────────────────────────────────────
    review = []

    def due(what, asof, after, note):
        age = None
        if asof:
            age = (today - datetime.strptime(asof, '%Y-%m-%d').date()).days
            if age <= after:
                return
        review.append({'what': what, 'asof': asof, 'age_days': age, 'note': note})

    ind_c = card(doc, 'India 10-year G-sec')
    due("India's 10-year G-sec", (ind_c or {}).get('asof'), 20,
        'Still a hand job. FBIL is the official source but sits behind a login and bars '
        'commercial use; worldgovernmentbonds.com renders its table in JavaScript, so a '
        'build box sees no numbers. Read the level and the change since 1 January off '
        'either, and update the scoreboard tile with it too.')
    due('RBI repo rate and stance', (repo_c or {}).get('asof'), 45,
        'Moves only at an MPC meeting, so check the date of the last one. The stance '
        'wording matters as much as the rate: it is the sentence that tells a reader '
        'which way the next move leans.')
    due('CPI inflation', (cpi_c or {}).get('asof'), 35,
        'MoSPI publishes around the 12th of each month. Note that there is no official '
        'core series, so if the card shows a core figure it has to name whose estimate '
        'it is.')
    due('The behaviour gap', doc.get('updated'), 100,
        'DSP Netra. Licensed, with no open source, and it does not appear in every '
        'edition. Worth redoing once a quarter, and leave it alone if Netra has not '
        'moved.')
    due('Asset classes, and India against the world', doc.get('updated'), 40,
        'First Global Monthly Action Report. Licensed, no open source.')
    due('The writing: headline, opening, the chain, what we are watching',
        doc.get('updated'), 40,
        'The numbers above say what happened. These say what it meant, which is the '
        'part worth a person’s time.')

    # The two once-a-year constants. Everything else on the page is either
    # fetched or written; these are the only numbers that go quietly wrong by
    # sitting still, which is why they get their own nag every January.
    # Prose that contradicts the numbers printed above it is worse than prose
    # that is merely old, so this one names the live figure in the nag.
    nifty = next((t for t in doc.get('scoreboard', []) if t.get('k') == 'Nifty 50'), {})
    said = re.findall(r'(\d{1,2})\s*%', json.dumps(doc.get('short') or {}, ensure_ascii=False))
    if nifty.get('v') and said:
        review.append({'what': 'The short version, and the opening paragraph',
                       'asof': doc.get('updated'), 'age_days': None,
                       'note': f"These mention {', '.join(sorted(set(said)))}% while the "
                               f"scoreboard above them now reads {nifty['v']} for the Nifty. "
                               f"A reader sees both at once, so this is the first thing to "
                               f"change, ahead of any figure."})

    if doc.get('fx_year_open_year') != yr:
        review.append({'what': 'fx_year_open', 'asof': None, 'age_days': None,
                       'note': f'Set it to the FBIL USD/INR reference rate for 1 January '
                               f'{yr}, then set fx_year_open_year to {yr}. Every rupee '
                               f'figure on this page hangs off it, including both '
                               f'conversion tiles, so a wrong value here is wrong in '
                               f'three places at once.'})
    if doc.get('gold_year_open_year') != yr:
        review.append({'what': 'gold_year_open', 'asof': None, 'age_days': None,
                       'note': f'Set it to gold in dollars an ounce at the last close of '
                               f'{yr - 1}, then set gold_year_open_year to {yr}. The live '
                               f'price is fetched, but no free source gives us the history '
                               f'to measure it against.'})

    json.dump({'generated': today.isoformat(), 'edition': doc.get('edition'),
               'written': doc.get('updated'), 'items': review},
              open(REVIEW, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    json.dump(doc, open(TARGET, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'\n  updated {touched} auto fields; oldest of them is {oldest}')
    print('  every editorial field left exactly as written')

    if review:
        print(f'\n  ACTION NEEDED, {len(review)} item(s) only a person can do:')
        for r in review:
            age = f", {r['age_days']} days old" if r['age_days'] is not None else ''
            print(f"    · {r['what']}{age}")
        print(f'  the same list is in content/market-pulse-review.json')
    else:
        print('\n  nothing is waiting on a person')


if __name__ == '__main__':
    main()
