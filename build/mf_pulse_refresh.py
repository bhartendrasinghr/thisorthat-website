"""Build mf-pulse-data.json: every number on the MF Industry Pulse page.

The page has two halves and they live in different files on purpose.

  mf-pulse-data.json   this script owns it. Nobody edits it by hand. Every
                       figure is read from AMFI's own files, so there is no
                       step where a number is retyped and can go wrong.
  content/mf-pulse.json  the CMS owns it: the sentences, the AMC leaderboard,
                       the fortnight's news. A person writes those.

Sources, all free and official:
  portal.amfiindia.com/spages/am<mon><yyyy>repo.xls
      AMFI's monthly report. The whole flows table: every category's sales,
      redemptions, net flow, AUM, folios and scheme count, plus the NFO sheet.
      Published around the 10th for the month before.
  amfiindia.com/api/amfi-monthly-note  ->  the month's note PDF
      The SIP table, which is not in the spreadsheet: contribution, account
      count, SIP assets, and the run of consecutive positive equity months.
  amfiindia.com/api/total-industry-aum-tables?date=DD-MM-YYYY
      Industry and SIF totals, as JSON.
  nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv
      Nifty 50, for the market row.

Needs xlrd (reads .xls) and pypdf. Both are pure Python:
    pip install xlrd pypdf
The GitHub Action installs them. On Vercel the step is skipped, which is
harmless: the committed JSON is already current.

Run:  python3 build/mf_pulse_refresh.py
"""
import csv, io, json, os, re, sys, urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'mf-pulse-data.json')
CACHE = os.path.join(ROOT, 'build', '.amficache')

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'}
MON = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']


def get(url, timeout=60, referer=None):
    h = dict(UA)
    if referer:
        h['Referer'] = referer
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()


def cached(name, url, timeout=90):
    """AMFI's monthly files never change once published, so fetch each once."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        return open(path, 'rb').read()
    blob = get(url, timeout=timeout)
    if len(blob) < 20000:                       # AMFI serves a tiny 404 page
        raise FileNotFoundError(f'{url} is not published yet')
    open(path, 'wb').write(blob)
    return blob


# ─── the monthly spreadsheet ──────────────────────────────────────────────
UPPER_ROMAN = re.compile(r'^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)$')
LOWER_ROMAN = re.compile(r'^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii)$')


def _clean(s):
    """'Solution Oriented Schemes **' and 'Sub Total - II' both carry noise."""
    return re.sub(r'\s+', ' ', re.sub(r'[*#]+', '', str(s))).strip()


def _sheets(blob):
    import xlrd
    book = xlrd.open_workbook(file_contents=blob)
    return [book.sheet_by_index(i) for i in range(book.nsheets)]


def _col(sh, r, c):
    try:
        return _clean(sh.cell_value(r, c))
    except IndexError:
        return ''


def pick_sheet(blob, needle):
    """Find a sheet by what is in it, not by its name.

    Somebody at AMFI names these tabs by hand every month. Across eight files
    the flows tab has been called MCR, MCR_Report, MCR Monthly Report,
    MCR_MonthlyReport, AMFI MONTHLY and 'September 25'. Matching on the name
    would break the first time they typed something new, and it would break
    silently. Matching on a row label the table cannot do without does not.
    """
    for sh in _sheets(blob):
        for r in range(min(sh.nrows, 200)):
            for c in (0, 1, 2):
                if re.match(needle, _col(sh, r, c), re.I):
                    return sh
    raise LookupError(f'no sheet in this workbook has a row matching {needle!r}')


def parse_month(blob):
    """One AMFI monthly report -> {(block, section, category): {...}}.

    Three levels, and all three matter.

    block    'A' open ended, 'B' close ended, 'C' interval. Without it the
             parse is wrong rather than merely incomplete: in the current
             layout 'Growth/Equity Oriented Schemes' is a CLOSE ended section
             worth four thousand crore, and in the layout AMFI used until July
             2026 the same words were the main open-ended equity table worth
             thirty-eight lakh crore.
    section  'Equity Schemes', 'Index Funds', 'Other Schemes', ...
    category 'Small Cap Fund'. Section matters here too: the debt table and
             the equity table each have a row called 'Sectoral Fund'.
    """
    sh = pick_sheet(blob, r'grand total$')
    COLS = [('schemes', 2), ('folios', 3), ('sales', 4), ('redemption', 5),
            ('flow', 6), ('aum', 7), ('aaum', 8)]

    def row(r):
        out = {}
        for key, c in COLS:
            try:
                v = sh.cell_value(r, c)
                out[key] = float(v) if v != '' else None
            except (IndexError, ValueError, TypeError):
                out[key] = None
        return out

    data, block, section = {}, None, None
    for r in range(sh.nrows):
        sr = _col(sh, r, 0)
        name = _col(sh, r, 1)
        if not name:
            continue
        vals = row(r)
        has_numbers = vals['aum'] is not None or vals['flow'] is not None

        if name.lower().startswith('grand total'):
            data[('TOTAL', 'TOTAL', 'industry')] = vals
            continue
        if re.match(r'^total\s+[ABC]\b', name, re.I):
            data[(sr or 'A', 'TOTAL', 'block')] = vals
            continue
        if re.match(r'^sub ?total', name, re.I):
            if block and section:
                data[(block, section, 'TOTAL')] = vals
            continue
        if re.match(r'^[ABC]$', sr) and not has_numbers:
            block, section = sr, None
            continue
        if UPPER_ROMAN.match(sr):
            section = name
            # A one-line section, like 'C / I / Income Oriented', carries its
            # own numbers and has no sub total row to follow.
            if has_numbers:
                data[(block, section, 'TOTAL')] = vals
            continue
        if LOWER_ROMAN.match(sr) and section and has_numbers:
            data[(block, section, name)] = vals
    return data


# AMFI renamed its own sections in August 2026, when the new scheme
# categorisation came in. Both spellings have to resolve to the same segment,
# and only inside the open-ended block.
SEG_PATTERNS = {
    'debt':   r'^(income/debt oriented schemes|debt schemes)$',
    'equity': r'^(growth/equity oriented schemes|equity schemes)$',
    'hybrid': r'^hybrid schemes$',
    'index':  r'^index funds$',
    'etf':    r'^exchange traded funds',
    'other':  r'^other schemes$',
    'overseas_fof': r'^(overseas fund of funds|fund of funds investing overseas)$',
}


def _section_total(data, pattern, block='A'):
    for (b, section, cat), vals in data.items():
        if b == block and cat == 'TOTAL' and re.match(pattern, section, re.I):
            return vals
    return {}


def _category(data, section_pattern, cat_pattern, block='A'):
    for (b, section, cat), vals in data.items():
        if (b == block and re.match(section_pattern, section, re.I)
                and re.match(cat_pattern, cat, re.I)):
            return vals
    return {}


def _add(*rows):
    out = {}
    for k in ('schemes', 'folios', 'sales', 'redemption', 'flow', 'aum', 'aaum'):
        vals = [r.get(k) for r in rows if r.get(k) is not None]
        out[k] = sum(vals) if vals else None
    return out


def _sub(a, b):
    out = {}
    for k in ('schemes', 'folios', 'sales', 'redemption', 'flow', 'aum', 'aaum'):
        if a.get(k) is None:
            out[k] = None
        else:
            out[k] = a[k] - (b.get(k) or 0)
    return out


def segment(data, which):
    """One of debt / equity / hybrid / passive, whatever the sheet calls it.

    Passive is the awkward one. Since August 2026 AMFI gives index funds and
    ETFs their own sections and it is simply the two added. Before that both
    sat inside 'Other Schemes' alongside overseas fund of funds, which is not
    a passive product, so that one row comes back out.
    """
    if which in ('debt', 'equity', 'hybrid'):
        return _section_total(data, SEG_PATTERNS[which])
    if which == 'passive':
        idx = _section_total(data, SEG_PATTERNS['index'])
        etf = _section_total(data, SEG_PATTERNS['etf'])
        if idx or etf:
            return _add(idx, etf)
        other = _section_total(data, SEG_PATTERNS['other'])
        if not other:
            return {}
        return _sub(other, _category(data, SEG_PATTERNS['other'], SEG_PATTERNS['overseas_fof']))
    if which == 'industry':
        return data.get(('TOTAL', 'TOTAL', 'industry')) or {}
    raise KeyError(which)


def month_file(d):
    return f'am{MON[d.month - 1]}{d.year}repo.xls'


def load_month(d):
    name = month_file(d)
    return parse_month(cached(name, f'https://portal.amfiindia.com/spages/{name}'))


def parse_nfo(blob):
    """The new-scheme sheet: what launched this month, and what it gathered.

    AMFI prints its own totals at the bottom and they are the figures to quote:
    a 'Total' for mutual fund schemes, a second 'Total' under the domestic
    fund-of-funds block, and a 'Grand Total' adding the two. Re-adding the rows
    by hand would only invent a third number nobody published.
    """
    try:
        sh = pick_sheet(blob, r'(type and category of the scheme|name of the schemes)')
    except LookupError:
        return None

    groups, order, in_fof = {}, [], False
    totals = {}
    for r in range(sh.nrows):
        label, name = _col(sh, r, 0), _col(sh, r, 1)
        try:
            n = float(sh.cell_value(r, 2)); amt = float(sh.cell_value(r, 3))
        except (ValueError, TypeError, IndexError):
            n = amt = None

        if re.match(r'fund of funds scheme', label, re.I) and n is None:
            in_fof = True
        if re.match(r'^grand total', label, re.I) and n is not None:
            totals['grand'] = {'count': int(n), 'raised': round(amt, 2)}
            continue
        if re.match(r'^total$', label, re.I) and n is not None:
            totals['fof' if in_fof else 'mf'] = {'count': int(n), 'raised': round(amt, 2)}
            continue
        m = re.match(r'^sub ?total\s*[-:]?\s*(.*)$', label, re.I)
        if m and n is not None:
            key = _clean(m.group(1)) or 'other'
            groups[key] = {'count': int(n), 'raised': round(amt, 2)}
            order.append(key)
            continue

    if not totals.get('grand') and not totals.get('mf'):
        return None
    return {'groups': [dict(k=k, **groups[k]) for k in order],
            'mf': totals.get('mf'), 'fof': totals.get('fof'),
            'grand': totals.get('grand') or totals.get('mf')}


# ─── the note PDF, for SIP ────────────────────────────────────────────────
def note_url(d):
    j = json.loads(get('https://www.amfiindia.com/api/amfi-monthly-note', timeout=45))
    want = f'{d:%B}-{d.year}'.lower()
    for fy in j.get('data', []):
        for item in fy.get('items', []):
            if (item.get('monthtitle') or '').strip().lower() == want:
                return item.get('pdfurl')
    return None


def parse_sip(pdf_bytes):
    """The 'SIP trend' table gives seven months at once, newest first."""
    from pypdf import PdfReader
    text = ''
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        t = page.extract_text() or ''
        if 'SIP trend' in t or 'contributing SIP accounts' in t:
            text += '\n' + t
    if not text:
        return None

    def series(label, cast=float):
        m = re.search(re.escape(label) + r'[^\n]*?((?:\s*[\d,]+\.?\d*){3,})', text)
        if not m:
            return None
        nums = re.findall(r'[\d,]+\.?\d*', m.group(1))
        return [cast(n.replace(',', '')) for n in nums]

    accounts = series('Number of contributing SIP accounts')
    contrib = series('SIP monthly contribution')
    assets = series('SIP assets (Rs lakh crore)') or series('SIP assets')
    share = series('SIP assets as a percentage')
    months = re.findall(r'([A-Z][a-z]{2})-(\d{2})', text)
    if not (accounts and contrib):
        return None

    out = {'months': [f'{a}-{b}' for a, b in months[:len(contrib)]],
           'accounts': accounts, 'contribution': contrib,
           'assets': assets, 'share': share}
    m = re.search(r'(\d+)\s*(?:st|nd|rd|th)\s+consecutive month', text)
    if m:
        out['equity_streak'] = int(m.group(1))
    return out


def parse_streak(pdf_bytes):
    from pypdf import PdfReader
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages[:4]:
        m = re.search(r'(\d+)\s*(?:st|nd|rd|th)\s+consecutive month', page.extract_text() or '')
        if m:
            return int(m.group(1))
    return None


# ─── the JSON totals, for SIF ─────────────────────────────────────────────
def industry_api(d):
    try:
        j = json.loads(get(f'https://www.amfiindia.com/api/total-industry-aum-tables?date={d:%d-%m-%Y}',
                           timeout=45))
        return j.get('data')
    except Exception:
        return None


# ─── NSE, for the market row ──────────────────────────────────────────────
def nifty(d):
    try:
        raw = get(f'https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv',
                  timeout=45, referer='https://www.nseindia.com/')
    except Exception:
        return None
    for r in csv.DictReader(io.StringIO(raw.decode('utf-8', 'replace'))):
        if (r.get('Index Name') or '').strip() == 'Nifty 50':
            try:
                return float(r['Closing Index Value'])
            except (KeyError, ValueError):
                return None
    return None


def nifty_back(start, limit=10):
    d = start
    for _ in range(limit):
        v = nifty(d)
        if v:
            return d, v
        d -= timedelta(days=1)
    return None, None


# ─── helpers ──────────────────────────────────────────────────────────────
def pct(now, then):
    if now is None or then in (None, 0):
        return None
    return round((now / then - 1) * 100, 1)


def eom(d):
    nxt = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def back(d, n):
    """n months before d, as a first-of-month date."""
    m = d.month - 1 - n
    return date(d.year + m // 12, m % 12 + 1, 1)


# The thirteen equity categories as AMFI names them since August 2026, and
# how the page says it. Month-on-month works because August is the first month
# of the new taxonomy; a year-on-year by category is not possible yet, because
# a year ago 'Value Fund/Contra Fund' and 'Sectoral/Thematic Funds' were each
# one line.
EQUITY_CATS = [
    (r'small cap fund', 'Small cap'), (r'mid cap fund', 'Mid cap'),
    (r'flexi cap fund', 'Flexi cap'), (r'large & mid cap fund', 'Large and mid cap'),
    (r'multi cap fund', 'Multi cap'), (r'sectoral fund', 'Sectoral'),
    (r'thematic fund', 'Thematic'), (r'focused fund', 'Focused'),
    (r'value fund$', 'Value'), (r'large cap fund', 'Large cap'),
    (r'dividend yield fund', 'Dividend yield'), (r'contra fund', 'Contra'),
    (r'elss', 'ELSS tax saver'),
]
# Each passive row: where to find it now, what to call it, and where to find
# the same thing a year ago. Only gold has an honest year-ago match. Until
# August 2026 AMFI reported silver, equity and every other ETF as a single
# 'Other ETFs' line, and lumped equity and debt index funds together, so a
# year-on-year for those would be comparing a part with a whole.
PASSIVE_ROWS = [
    ('etf', r'equity etf', 'Equity ETF', None),
    ('etf', r'gold etf', 'Gold ETF', ('other', r'gold etf')),
    ('index', r'equity funds', 'Equity index fund', None),
    ('etf', r'silver etf', 'Silver ETF', None),
    ('etf', r'debt etf', 'Debt ETF', None),
    ('index', r'debt funds', 'Debt index fund', None),
]


def main():
    print('→ Finding the latest AMFI monthly report')
    latest, months = None, {}
    probe = date.today().replace(day=1)
    for i in range(4):
        d = back(probe, i)
        try:
            months[d] = load_month(d)
            latest = d
            break
        except Exception as e:
            print(f'  {month_file(d)}: {e}')
    if not latest:
        sys.exit('  no AMFI monthly report reachable; nothing written')
    print(f'  latest published: {latest:%B %Y}')

    # Six months before it, for the flows table, plus the same month last year.
    for d in [back(latest, i) for i in range(1, 7)] + [back(latest, 12)]:
        if d in months:
            continue
        try:
            months[d] = load_month(d)
        except Exception as e:
            print(f'  {month_file(d)} skipped: {e}')

    cur = months[latest]
    prev = months.get(back(latest, 1), {})
    yago = months.get(back(latest, 12), {})
    asof = eom(latest)

    doc = {
        'generated': date.today().isoformat(),
        'month': f'{latest:%B %Y}',
        'month_short': f'{latest:%b %Y}',
        'asof': asof.isoformat(),
        'prev_month_short': f'{back(latest, 1):%b %Y}',
        'year_ago_short': f'{back(latest, 12):%b %Y}',
        'source_file': month_file(latest),
        # AMFI publishes a month's figures around the 10th of the month after
        # it. So the month shown here is normally one behind the calendar, and
        # a reader landing on 1 November should be told that rather than left
        # to wonder whether the page is broken.
        'next_month': f'{back(latest, -1):%B %Y}',
        'next_due': date(back(latest, -2).year, back(latest, -2).month, 10).isoformat(),
    }

    def seg3(which):
        return (segment(cur, which), segment(prev, which), segment(yago, which))

    # ── headline ──
    ind, ind_p, ind_y = seg3('industry')
    eq, eq_p, _ = seg3('equity')
    pas, pas_p, _ = seg3('passive')
    doc['industry'] = {
        'aum': ind.get('aum'), 'aum_prev': ind_p.get('aum'),
        'aum_mom': pct(ind.get('aum'), ind_p.get('aum')),
        'aum_yoy': pct(ind.get('aum'), ind_y.get('aum')),
        'flow': ind.get('flow'), 'flow_prev': ind_p.get('flow'),
        'folios': ind.get('folios'), 'folios_prev': ind_p.get('folios'),
        'schemes': ind.get('schemes'),
    }
    doc['equity'] = {'flow': eq.get('flow'), 'flow_prev': eq_p.get('flow'),
                     'flow_mom': pct(eq.get('flow'), eq_p.get('flow'))}
    doc['passive'] = {
        'flow': pas.get('flow'), 'flow_prev': pas_p.get('flow'),
        'flow_mom': pct(pas.get('flow'), pas_p.get('flow')), 'aum': pas.get('aum'),
        'share': round(100 * pas['aum'] / ind['aum'], 1) if pas.get('aum') and ind.get('aum') else None,
    }

    # ── AUM by segment ──
    doc['segments'] = []
    for label, which in [('Equity', 'equity'), ('Debt', 'debt'),
                         ('Passive (index + ETF)', 'passive'), ('Hybrid', 'hybrid'),
                         ('Industry', 'industry')]:
        now, was, yr = seg3(which)
        row = {'k': label, 'aum': now.get('aum'), 'aum_prev': was.get('aum'),
               'mom': pct(now.get('aum'), was.get('aum')),
               'yoy': pct(now.get('aum'), yr.get('aum'))}
        if which == 'industry':
            row['total'] = True
        doc['segments'].append(row)
        if row['yoy'] is None:
            print(f'  no year-ago figure for {label}')

    # ── the thirteen equity categories, biggest inflow first ──
    cats = []
    for pattern, label in EQUITY_CATS:
        now = _category(cur, SEG_PATTERNS['equity'], pattern)
        was = _category(prev, SEG_PATTERNS['equity'], pattern)
        if not now:
            print(f'  equity category not in the sheet: {label}')
            continue
        cats.append({'k': label, 'flow': now.get('flow'), 'flow_prev': was.get('flow'),
                     'aum': now.get('aum'), 'aum_mom': pct(now.get('aum'), was.get('aum')),
                     'folios': now.get('folios'), 'schemes': now.get('schemes')})
    doc['equity_cats'] = sorted(cats, key=lambda c: -(c['flow'] or 0))
    eq_sum = sum(c['flow'] for c in cats if c['flow'] is not None)
    if eq.get('flow') and abs(eq_sum - eq['flow']) > 1:
        print(f"  WARNING: the thirteen categories add to {eq_sum:,.0f} cr, "
              f"the sheet's equity total is {eq['flow']:,.0f} cr")
    else:
        print('  the thirteen equity categories add up to the sheet total')

    # ── passive detail ──
    rows = []
    for which, pattern, label, old_at in PASSIVE_ROWS:
        now = _category(cur, SEG_PATTERNS[which], pattern)
        was = _category(prev, SEG_PATTERNS[which], pattern)
        if not now:
            print(f'  passive row not in the sheet: {label}')
            continue
        yr = _category(yago, SEG_PATTERNS[which], pattern)
        if not yr and old_at:
            yr = _category(yago, SEG_PATTERNS[old_at[0]], old_at[1])
        rows.append({'k': label, 'flow': now.get('flow'), 'aum': now.get('aum'),
                     'aum_prev': was.get('aum'), 'folios': now.get('folios'),
                     'aum_yoy': pct(now.get('aum'), yr.get('aum')) if yr else None})
        if rows[-1]['aum_yoy'] is not None:
            print(f"  {label} assets {rows[-1]['aum_yoy']:+.1f}% on the year")
    doc['passive_rows'] = sorted(rows, key=lambda r: -(r['flow'] or 0))

    # ── seven months of flows ──
    print('→ Building the seven-month flow table')
    series = []
    for i in range(6, -1, -1):
        d = back(latest, i)
        m = months.get(d)
        if not m:
            continue
        series.append({'m': f'{d:%b %Y}', 'm_iso': eom(d).isoformat(),
                       'equity': segment(m, 'equity').get('flow'),
                       'debt': segment(m, 'debt').get('flow'),
                       'hybrid': segment(m, 'hybrid').get('flow'),
                       'passive': segment(m, 'passive').get('flow'),
                       'total': segment(m, 'industry').get('flow')})
    doc['months'] = series
    holes = [r['m'] for r in series if None in (r['equity'], r['debt'], r['hybrid'],
                                                r['passive'], r['total'])]
    if holes:
        print(f"  WARNING: incomplete months in the flow table: {', '.join(holes)}")
    else:
        print(f'  {len(series)} months, all five columns present')

    # ── new schemes ──
    try:
        nfo = parse_nfo(cached(month_file(latest),
                               f'https://portal.amfiindia.com/spages/{month_file(latest)}'))
        if nfo:
            doc['nfo'] = nfo
            g = nfo['grand']
            print(f"  new schemes: {g['count']} raising {g['raised']:,.0f} cr "
                  f"({', '.join(x['k'] + ' ' + str(x['count']) for x in nfo['groups'])})")
    except Exception as e:
        print(f'  new-scheme sheet skipped: {e}')

    # ── SIP, from the note ──
    print('→ Reading the SIP table out of the monthly note')
    try:
        url = note_url(latest)
        if not url:
            raise LookupError(f'no note listed for {latest:%B %Y}')
        pdf = cached(f'note-{latest:%Y-%m}.pdf', url, timeout=120)
        sip = parse_sip(pdf)
        if sip and sip.get('contribution'):
            doc['sip'] = sip
            doc['note_pdf'] = url
            if not sip.get('equity_streak'):
                st = parse_streak(pdf)
                if st:
                    doc['sip']['equity_streak'] = st
            print(f"  SIP {sip['contribution'][0]:,.0f} cr, {sip['accounts'][0]} cr accounts, "
                  f"equity streak {doc['sip'].get('equity_streak')}")
        else:
            print('  the SIP table did not parse; the page will leave that row out')
    except Exception as e:
        print(f'  SIP step skipped: {e}')

    # ── SIF, from the JSON API ──
    print('→ SIF totals')
    api_now, api_prev = industry_api(asof), industry_api(eom(back(latest, 1)))
    if api_now and api_now.get('sif'):
        sif, sif_p = api_now['sif'], (api_prev or {}).get('sif') or {}
        doc['sif'] = {
            'aum': sif.get('sif_net_assets_under_management'),
            'flow': sif.get('sif_net_inflow_outflow'),
            'schemes': sif.get('sif_no_of_schemes'),
            'folios': sif.get('sif_no_of_folios'),
            'mom': pct(sif.get('sif_net_assets_under_management'),
                       sif_p.get('sif_net_assets_under_management')),
        }
        print(f"  SIF AUM {doc['sif']['aum']:,.0f} cr, inflow {doc['sif']['flow']:,.0f} cr")
        # Cross-check the spreadsheet against AMFI's own JSON. Two different
        # publications of the same month should agree, and if they do not the
        # parse is wrong somewhere.
        api_aum = (api_now.get('mf_excluding_fof') or {}).get('mf_net_assets_under_management')
        if api_aum and ind.get('aum') and abs(api_aum - ind['aum']) > 1:
            print(f"  WARNING: sheet says {ind['aum']:,.2f} cr, API says {api_aum:,.2f} cr")
        elif api_aum:
            print('  cross-check passed: sheet and API agree on industry AUM')

    # ── the market row ──
    print('→ Nifty 50')
    d_now, n_now = nifty_back(date.today())
    if n_now:
        d_week, n_week = nifty_back(d_now - timedelta(days=7))
        d_year, n_year = nifty_back(d_now - timedelta(days=364))
        doc['market'] = {
            'nifty': n_now, 'asof': d_now.isoformat(),
            'week': pct(n_now, n_week), 'year': pct(n_now, n_year),
            'week_from': d_week.isoformat() if d_week else None,
            'year_from': d_year.isoformat() if d_year else None,
            'nifty_week_ago': n_week, 'nifty_year_ago': n_year,
        }
        print(f'  {n_now:,.0f} on {d_now}, week {doc["market"]["week"]}%, '
              f'52 weeks {doc["market"]["year"]}%')

    json.dump(doc, open(TARGET, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n  wrote {os.path.relpath(TARGET, ROOT)} for {doc["month"]}')


if __name__ == '__main__':
    main()
