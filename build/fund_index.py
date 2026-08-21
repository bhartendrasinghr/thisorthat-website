"""Build the fund index from AMFI's daily NAV file.

AMFI sends no CORS headers, so the browser cannot read it directly. The index is
fetched here at build time and written as a compact file the page can load.
Direct and Regular are the same fund, so they are merged into one row carrying
both scheme codes. Only growth options: IDCW NAVs are distorted by payouts and
would make the return figures wrong.
"""
import json, pathlib, re, urllib.request

URL = 'https://portal.amfiindia.com/spages/NAVAll.txt'
OUT = pathlib.Path(__file__).resolve().parent.parent / 'fund-index.json'


def short_category(g):
    m = re.search(r'\((.*)\)', g)
    g = m.group(1) if m else g
    return re.sub(r'^(Equity|Debt|Hybrid|Other|Solution Oriented|Index Funds|Fund of Funds)\s*'
                  r'Scheme(s)?\s*(\(Domestic\))?\s*-\s*', '', g).strip()


def clean_name(n):
    return re.sub(r'\s*-\s*(Direct|Regular)\s*Plan\s*', ' ', n).replace('  ', ' ').strip(' -')


def build(timeout=60):
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'ignore')
    except Exception as e:
        print(f'  Could not reach AMFI ({e}); keeping the existing index')
        return

    cat = house = ''
    funds, cats, houses = {}, [], []

    def idx(lst, v):
        if v not in lst: lst.append(v)
        return lst.index(v)

    stamp = ''
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('Scheme Code'):
            continue
        if ';' not in line:
            # a category header carries "Scheme" and brackets; anything else is a fund house
            if 'Scheme' in line and '(' in line: cat = line
            else: house = line
            continue
        p = line.split(';')
        if len(p) < 8 or not re.match(r'^\d+$', p[0]): continue
        if 'growth' not in p[5].lower(): continue
        if not cat.startswith('Open Ended'): continue
        try: nav = float(p[6])
        except ValueError: continue
        stamp = p[7].strip() or stamp
        key = (clean_name(p[3]), house)
        f = funds.setdefault(key, {'n': clean_name(p[3]), 'h': idx(houses, house),
                                   'c': idx(cats, short_category(cat)), 'd': None, 'r': None, 'v': nav})
        if 'direct' in p[4].lower(): f['d'] = p[0]
        else: f['r'] = p[0]

    rows = [[f['n'], f['h'], f['c'], f['d'], f['r'], round(f['v'], 4)] for f in funds.values()]
    rows.sort(key=lambda x: x[0].lower())
    OUT.write_text(json.dumps({'asOf': stamp, 'cats': cats, 'houses': houses, 'funds': rows},
                              separators=(',', ':')), encoding='utf-8')
    print(f'  Fund index: {len(rows)} funds, {len(cats)} categories, as of {stamp} '
          f'({OUT.stat().st_size / 1024:.0f} KB)')


if __name__ == '__main__':
    build()
