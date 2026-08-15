#!/usr/bin/env python3
"""
ThisOrThat with Bhartendra — YouTube channel sync.

Usage:   python3 sync.py
Result:  rewrites episodes.js with the latest videos from the channel,
         preserving any guest/category overrides defined below.

Run this whenever a new episode goes up. The website auto-renders from
episodes.js, so the rest of the site updates instantly.
"""
import json, re, sys, os, urllib.request
from datetime import datetime, timezone

CHANNEL_HANDLE = '@ThisOrThatPodcastIndia'
CHANNEL_ID = 'UC3JSfV8-K_ns4XI3uqfbrCQ'
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'episodes.js')

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# ─── Uploads that are NOT full episodes (clips, shorts, trailers) ────────
# Anything listed here is dropped from episodes.js entirely.
EXCLUDE_IDS = {
    'RqCy5D4f1Mg',  # "Active vs Passive Funds" - a clip, not a full podcast (per Bhartendra)
    'dnriwRGaVJA',  # "What return should you really expect" - a Roopa Venkatkrishnan clip, description says "In this clip"
}

# ─── Manual guest overrides ──────────────────────────────────────────────
# When auto-parsing can't reliably extract the guest from the title, use these.
# Keyed by YouTube video ID. Use "Bhartendra (solo)" for solo episodes.
GUEST_OVERRIDES = {
    # Episodes where guest is named in title but wasn't auto-extracted:
    'tbQBKyeGydU': 'Aashish Sommaiya',      # Ep 60 - title spells Somaiyaa; profile name is Sommaiya
    'GFtYcvEftNQ': 'Roopa Venkatkrishnan',  # Ep 58 - SIP for 30 years (was mis-tagged solo)
    'qR1CZ2dWr5Q': 'Anupam Tiwari',         # Ep 55 — "Groww MF's Equity Head Answers"
    'Bnv2OOb5irs': 'Bhalchandra Joshi',     # Ep 57 — "30 Years of MF Lessons | Bhalchandra Joshi"
    'vIL33wnD5lk': 'Debashish Bose',        # Ep 53
    'ax-QZl75dbA': 'Kalpen Parekh',         # Ep 49
    'ldoFnNk6Z2g': 'Kirtan Shah',           # Ep 47
    '8jqbn8N1zeY': 'Neil Borate',           # Ep 46
    'LULE5jPzlo0': 'Thomas Priju',          # Ep 36
    'nT_TwhuIEPo': 'Mohit Bhatia',          # Ep 35
    'pGdux5kFP3U': 'CA Anuj Jain',          # Ep 30
    'YOwd-k4VGPM': 'Neil Borate',           # Ep 29
    '07c7HDPBUBE': 'Sneha Jain',            # Ep 10
    '3KvDSkQu-IY': 'Niranjan Avasthi',      # Ep 11 (NEW guest)
    'WhrfDxA1d7A': 'Mahavir Chopra',        # Ep 7
    'U9ZrWEL-Jqo': 'Shaymali Basu',         # Ep 3 (NEW guest)
    # Episodes already correctly attributed via override:
    'seqzo4v-mlE': 'Vinayak Sapre',
    '6H6GsUjCWfE': 'Sneha Jain',
    'baM9f9oeNEc': 'Devina Mehra',
    'HX4Ln_yjQBc': 'Pooja Bhinde',
    'ukI6xDsrjyI': 'Ajit Menon',
    'Fy5Wzb40QhQ': 'Dhirendra Kumar',
    'oJ0kHSqJaqc': 'Vijai Mantri',
    'jg9yRvRDqW0': 'Lisa Pallavi Barbora',
    'LJBgwAlx_MM': 'Mahavir Chopra',
    'y467zmb9coo': 'Kirtan Shah',
    'qCMA_zCb-38': 'Aashish Sommaiya',
    'Ms_2WqYOIsY': 'Abhijit More',
    '_pO65w9FnTo': 'Swarup Mohanty',        # Ep 12 — name not in title
    'OlrHz1Og_kY': 'Nimesh Chandan',       # Ep 13 — name is after the pipe, which sync strips
    '7RURrUgKXig': 'Abhijit More',          # Ep 27 — hidden home-buying costs (title does not name him)
    'YH2ZegF1ewk': 'Mrin Agarwal',
    '2IFKptd2Qyw': 'Raghav Iyengar',
    # Confirmed solo / compilation episodes:
    'IbD02i7Xvys': 'Bhartendra (solo)',     # Ep 52 — SIP isn't the problem
    '63j2xg2IGUU': 'Bhartendra (solo)',     # Ep 48 — 5 lessons from 40 experts (compilation)
    'p-fDdN8Tm6w': 'Bhartendra (solo)',     # Ep 45 — Budget 2026
    'an4dvf0llMM': 'Bhartendra (solo)',     # Ep 44 — Markets are flat
    'dkQ9JW-Py9A': 'Bhartendra (solo)',     # Ep 42 — Retirement risk
    '0YwE4R-qPqA': 'Bhartendra (solo)',     # Ep 39 — Buy vs rent (panel compilation)
    '9SvVl5FALK4': 'Bhartendra (solo)',     # Ep 38 — Couple's portfolio (interviewees not named)
    'QApks7nfIYI': 'Bhartendra (solo)',     # Ep 34 — Ordinary investors
    '0zxhAUjt-38': 'Bhartendra (solo)',     # Ep 32 — PF stuck
    'ejC8nevgQb0': 'Bhartendra (solo)',     # Ep 25 — Where to invest 2025
    '7YdiFShGRRQ': 'Bhartendra (solo)',     # Ep 24 — Wealth with limited income
    'C966CXKS_tU': 'Bhartendra (solo)',     # Ep 23 — Retirement scares us
    'jCRb7WpH6h4': 'Bhartendra (solo)',     # Ep 22 — Find your number
    'o1_3k5EkzZg': 'Bhartendra (solo)',     # Ep 21 — Rupee falling
    'ch96iqz4wj8': 'Bhartendra (solo)',     # Ep 17 — 10 crore SIP (guest name not in title)
}

# ─── CMS-editable overrides ──────────────────────────────────────────────
# content/episode-overrides.json is edited through /admin (Episode Overrides).
# Anything set there wins over the defaults above, so a guest or category can
# be corrected without touching this file.
def load_cms_overrides():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content', 'episode-overrides.json')
    guests, cats, titles = {}, {}, {}
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        print(f'  Could not read episode-overrides.json ({e}), using built-in defaults only')
        return guests, cats, titles
    for row in data.get('overrides') or []:
        vid = (row.get('video_id') or '').strip()
        if not vid:
            continue
        if (row.get('guest') or '').strip():    guests[vid] = row['guest'].strip()
        if (row.get('category') or '').strip(): cats[vid]   = row['category'].strip()
        if (row.get('title') or '').strip():    titles[vid] = row['title'].strip()
    print(f'  Loaded {len(guests)} guest, {len(cats)} category, {len(titles)} title overrides from the CMS')
    return guests, cats, titles

CMS_GUESTS, CMS_CATS, CMS_TITLES = load_cms_overrides()
GUEST_OVERRIDES.update(CMS_GUESTS)

def load_cms_roles():
    """Roles come from the guest profiles the CMS edits, so adding a profile is
    enough. The dict below is only a fallback for guests with no profile yet."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'content', 'guests.json')
    try:
        with open(path, encoding='utf-8') as fh:
            return {g['name']: g['role'] for g in json.load(fh) if g.get('name') and g.get('role')}
    except Exception:
        return {}


# Guest → role/title. Fallback only; the CMS profile wins.
GUEST_ROLES = {
    'Vijai Mantri': 'Founder, VMFS',
    'Debashish Bose': 'Founder & Managing Partner, Infinite Circle Asset Manager',
    'Krishnan Sharma': 'Financial Coach',
    'Mahmood Basha Shaik': 'Head International Business, Baroda BNP Paribas',
    'Kalpen Parekh': 'CEO, DSP Mutual Fund',
    'Kirtan Shah': 'Founder, Credence Wealth, Mutual Fund Distributor',
    'Neil Borate': 'Founder, thefynprint',
    'Karan Datta': 'Former CBO, Axis Mutual Fund',
    'Thomas Priju': 'Fund Manager',
    'Mohit Bhatia': 'CEO, Bank of India MF',
    'Vinayak Sapre': 'Financial Coach',
    'Chirag Barjatya': 'Founder, PFC, Fitness Coach',
    'CA Anuj Jain': 'Fund Manager & Founder, Green Portfolio',
    'Sneha Jain': 'Fund Manager',
    'Devina Mehra': 'Founder, First Global',
    'Pooja Bhinde': 'Certified Financial Planner',
    'Ajit Menon': 'Former CEO, PGIM Mutual Fund',
    'Dhirendra Kumar': 'CEO, Value Research',
    'Lisa Pallavi Barbora': 'Content Creator, Author',
    'Mahavir Chopra': 'Founder, Beshak.org',
    'Aashish Sommaiya': 'Equity Partner, WhiteOak Capital Group; ED & CEO, WhiteOak Capital Asset',
    'Abhijit More': 'Real Estate',
    'Roopa Venkatkrishnan': 'Director, Sapient Wealth Advisors and Brokers Pvt Ltd',
    'Raghav Iyengar': 'CEO, 360 One AMC',
    'Mrin Agarwal': 'Founder, Finsafe',
    'Niranjan Avasthi': 'Head of Product & Marketing, Edelweiss MF',
    'Shaymali Basu': 'Financial Planner',
    'Anupam Tiwari': 'Head of Equities, Groww Mutual Fund',
    'Bhalchandra Joshi': 'Mutual Fund Veteran, COO The Wealth Company',
    'Swarup Mohanty': 'Vice Chairman & CEO, Mirae Asset Investment Managers',
}

# ─── Fetch from YouTube ──────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    return urllib.request.urlopen(req).read().decode()

def fetch_channel_videos():
    html = fetch(f'https://www.youtube.com/@{CHANNEL_HANDLE.lstrip("@")}/videos')
    m = re.search(r'var ytInitialData = ({.*?});</script>', html)
    if not m: raise RuntimeError('Could not find ytInitialData on channel page')
    data = json.loads(m.group(1))
    api_key = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html).group(1)
    client_version = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', html).group(1)

    tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
    all_videos = []
    for t in tabs:
        if 'tabRenderer' in t and t['tabRenderer'].get('title','').lower() == 'videos':
            content = t['tabRenderer']['content']['richGridRenderer']['contents']
            vids, cont = parse_items(content)
            all_videos.extend(vids)
            # Paginate
            while cont:
                payload = json.dumps({
                    'context': {'client': {'clientName':'WEB','clientVersion':client_version}},
                    'continuation': cont
                }).encode()
                req = urllib.request.Request(
                    f'https://www.youtube.com/youtubei/v1/browse?key={api_key}',
                    data=payload,
                    headers={'Content-Type':'application/json','User-Agent':UA}
                )
                resp = json.loads(urllib.request.urlopen(req).read())
                new_content = []
                for a in resp.get('onResponseReceivedActions', []):
                    if 'appendContinuationItemsAction' in a:
                        new_content = a['appendContinuationItemsAction']['continuationItems']
                vids2, cont = parse_items(new_content)
                all_videos.extend(vids2)
                if not vids2: break
            break
    return all_videos

def parse_items(content):
    out, cont = [], None
    for item in content:
        if 'continuationItemRenderer' in item:
            cont = item['continuationItemRenderer']['continuationEndpoint']['continuationCommand']['token']
            continue
        if 'richItemRenderer' not in item: continue
        lvm = item['richItemRenderer']['content'].get('lockupViewModel')
        if not lvm: continue
        vid = lvm.get('contentId')
        md = lvm.get('metadata', {}).get('lockupMetadataViewModel', {})
        title = md.get('title', {}).get('content', '')
        rows = md.get('metadata', {}).get('contentMetadataViewModel', {}).get('metadataRows', [])
        stats = []
        for r in rows:
            for p in r.get('metadataParts', []):
                txt = p.get('text', {}).get('content', '')
                if txt: stats.append(txt)
        out.append({'id': vid, 'title': title, 'stats': stats})
    return out, cont

# ─── Cleaning helpers ────────────────────────────────────────────────────
def parse_views(stats):
    for s in stats:
        m = re.match(r'^([\d.,]+[KMk]?)\s+views?$', s.strip())
        if m: return m.group(1)
    return None

def parse_published(stats):
    for s in stats:
        if 'ago' in s: return s
    return None

NEW_GUESTS_SEEN = []

_NOT_A_NAME = re.compile(
    r'\b(part|mutual|fund|funds|investing|investment|explained|india|indian|money|wealth|sip|'
    r'guide|truth|lessons|strategy|plan|tips|smart|hindi|english|podcast|episode|full|ft|feat|'
    r'ceo|cio|founder|director|head)\b', re.I)


def _looks_like_a_person(s):
    words = s.split()
    if not (2 <= len(words) <= 4):        return False
    if _NOT_A_NAME.search(s):             return False
    if re.search(r'\d', s):               return False
    return all(w[:1].isupper() for w in words)


def guest_from_title(title, known):
    """These titles almost always end with the guest: '... | Gajendra Kothari'.
    The parser never read them, which is why a new guest defaulted to solo and
    stayed that way until somebody noticed and added an override by hand.
    """
    parts = re.split(r'\s*[|\u2013\u2014]\s*|\s+I\s+', title)
    if len(parts) < 2:
        return None
    tail = parts[-1].strip(' .!?-').split(',')[0].strip()   # drop a trailing ", CEO WealthTrust"
    if not tail:
        return None
    if tail in known:
        return tail
    if not _looks_like_a_person(tail):
        return None
    # Spelling drifts between titles, so Somaiyaa and Sommaiya must not become
    # two people. Snap to an existing guest when it is clearly the same person.
    import difflib
    close = difflib.get_close_matches(tail, list(known), n=1, cutoff=0.85)
    if close:
        return close[0]
    if tail not in NEW_GUESTS_SEEN:
        NEW_GUESTS_SEEN.append(tail)
    return tail


def parse_guest(vid, title, stats, known=()):
    if vid in GUEST_OVERRIDES:
        return GUEST_OVERRIDES[vid]
    for s in stats:
        m = re.match(r'ThisOrThat with Bhartendra and (.+?)(?:\s*-.*)?$', s)
        if m:
            return m.group(1).strip().replace('Krishan Sharma', 'Krishnan Sharma').replace('Mahamood', 'Mahmood')
    from_title = guest_from_title(title, known)
    if from_title:
        return from_title
    return 'Bhartendra (solo)'  # default if unclear


def clean_title(title):
    t = title
    t = re.sub(r'\s*[\|I]+\s*(ThisorThat|This or That|ThisOrThat)[^|]*$', '', t, flags=re.I)
    t = re.sub(r'\s*\|\s*[Tt]his\s*[Oo]r\s*[Tt]hat.*$', '', t)
    t = re.sub(r'\s*I\s+Episode\s+\d+.*$', '', t)
    t = re.sub(r'\s*\|\s*Episode\s+\d+.*$', '', t)
    t = re.sub(r'\s*I\s+Ep\d+.*$', '', t)
    t = re.sub(r'#\w+\s*', '', t)
    t = re.sub(r'\s*[\|I]\s*[Ff][Tt]\.?\s+[A-Z][^\|]*$', '', t)
    t = re.sub(r'\s*[Ff][Tt]\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+.*$', '', t)
    t = re.sub(r'\s+', ' ', t).strip(' |-—,')
    return t

def categorize(title):
    """Guess a category from the title. First rule that matches wins, so the order
    is the design: a specific subject sits above a general one, and Investing is
    last because almost every title on this channel mentions investing. Anything
    here can be overridden per episode from the CMS, which always wins.
    """
    t = title.lower()
    def hit(words):
        return any(re.search(r'\b' + re.escape(w) + r'\b', t) for w in words)

    # a named subject
    if hit(['crypto', 'bitcoin', 'ethereum', 'stablecoin', 'stablecoins', 'blockchain', 'web3']): return 'Crypto'
    if hit(['insurance', 'mediclaim', 'term plan']):                                              return 'Insurance'
    if hit(['fitness', 'gym', 'workout', 'exercise']):                                            return 'Fitness'
    if hit(['health', 'unhealthy', 'wellness', 'medical']):                                       return 'Health'
    if hit(['aif', 'pms', 'reit', 'invit', 'unlisted', 'alternate', 'alternates',
            'private equity', 'startup', 'angel']):                                               return 'Alternates'
    if hit(['retire', 'retirement', 'pension', 'pf', 'epf', 'nps']):                              return 'Retirement'
    if hit(['gold', 'silver', 'metal', 'metals']):                                                return 'Commodities'
    if hit(['global', 'us', 'nasdaq', 'dollar', 'magnificent', 'abroad',
            'international']) or 'india is not' in t:                                             return 'Global'
    if hit(['real estate', 'house', 'home', 'rent', 'property', 'घर']):                           return 'Real Estate'
    if hit(['budget', 'tax', 'ltcg']):                                                            return 'Tax'
    if hit(['career', 'job', 'salary', 'appraisal', 'promotion', 'freelance', 'side hustle']):    return 'Career'

    # how a person behaves sits above what they hold, because the angle is the point
    if hit(['mistake', 'mistakes', 'mindset', 'panic', 'emotion', 'emotions', 'women',
            'behavior', 'behavioral', 'behaviour', 'patience', 'discipline', 'hidden',
            'simple', 'scares', 'fear', 'greed', 'fomo']):                                        return 'Behaviour'

    # what they hold
    if hit(['sip', 'sips', 'step-up', 'stp', 'swp']):                                             return 'SIP'
    if hit(['mutual fund', 'mutual funds', 'nfo', 'amc', 'expense ratio',
            'fund manager', 'index fund', 'elss']):                                               return 'Mutual Fund'
    if hit(['market', 'markets', 'crash', 'crisis', 'correction', 'bond', 'yield']):              return 'Markets'
    if hit(['family', 'couple', 'wealth', 'financial freedom', 'crore', 'rich', 'crorepati']):    return 'Wealth'
    if hit(['equity', 'stock', 'stocks', 'portfolio', 'invest', 'investing',
            'investor', 'investors', 'fund', 'funds']):                                           return 'Investing'
    return 'Investing'


GUEST_ROLES.update(load_cms_roles())
# the names the CMS already knows, so a title can be matched against them
KNOWN_GUESTS = set(GUEST_ROLES.keys()) | set(CMS_GUESTS.values())


def initials_of(name):
    if not name or 'solo' in name.lower(): return 'BS'
    parts = [p for p in re.sub(r'^CA\s+|^Mr\.?\s+', '', name).split() if p and p[0].isupper()]
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()

# ─── Main ────────────────────────────────────────────────────────────────
def main():
    print(f'→ Syncing from YouTube channel {CHANNEL_HANDLE} …')
    raw = fetch_channel_videos()
    raw = [v for v in raw if v['id'] not in EXCLUDE_IDS]
    print(f'  Found {len(raw)} long-form episodes (after excluding clips)')

    episodes = []
    for i, v in enumerate(raw):
        ep_num = len(raw) - i
        episodes.append({
            'n': ep_num,
            'id': v['id'],
            'title': CMS_TITLES.get(v['id']) or clean_title(v['title']),
            'guest': parse_guest(v['id'], v['title'], v['stats'], KNOWN_GUESTS),
            'cat': CMS_CATS.get(v['id']) or categorize(v['title']),
            'views': parse_views(v['stats']),
            'published': parse_published(v['stats']),
            'thumb': f'https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg',
        })

    # Build guests aggregate
    from collections import defaultdict
    guest_eps = defaultdict(list)
    # Attributions that are not a person. A cut from several past episodes is
    # neither solo nor a guest, and must not turn into a guest profile.
    NOT_A_PERSON = ('solo', 'compilation')
    for e in episodes:
        g = (e['guest'] or '').lower()
        if e['guest'] and not any(t in g for t in NOT_A_PERSON):
            guest_eps[e['guest']].append(e['n'])

    bgs = ['bg-navy text-mustard','bg-mustard text-navy-ink','bg-alert text-cream','bg-navy-ink text-mustard']
    guests = []
    for i, (name, eps) in enumerate(sorted(guest_eps.items(), key=lambda x: -len(x[1]))):
        guests.append({
            'name': name,
            'role': GUEST_ROLES.get(name, 'Guest expert'),
            'initials': initials_of(name),
            'eps': len(eps),
            'ep_ids': eps,
            'bg': bgs[i % len(bgs)],
        })

    synced_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    with open(OUT_FILE, 'w') as f:
        f.write(f'// Auto-generated by sync.py from YouTube channel {CHANNEL_ID}\n')
        f.write(f'// Last synced: {synced_at}\n\n')
        f.write(f'window.SYNCED_AT = {json.dumps(synced_at)};\n')
        f.write(f'window.EPISODES = {json.dumps(episodes, indent=2, ensure_ascii=False)};\n\n')
        f.write(f'window.GUESTS = {json.dumps(guests, indent=2, ensure_ascii=False)};\n')

    print(f'  Wrote {len(episodes)} episodes, {len(guests)} guests → {os.path.basename(OUT_FILE)}')
    if NEW_GUESTS_SEEN:
        print('  New name(s) read from a title, with no guest profile yet:')
        for n in NEW_GUESTS_SEEN:
            print(f'      {n}   <- add a profile in the CMS, or override the episode if this is wrong')
    print(f'  Synced at {synced_at}')
    print()
    print('  Top guests:')
    for g in guests[:5]:
        print(f'    {g["eps"]}x  {g["name"]} ({g["role"]})')

if __name__ == '__main__':
    main()
