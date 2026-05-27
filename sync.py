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

# ─── Manual guest overrides ──────────────────────────────────────────────
# When auto-parsing can't reliably extract the guest from the title, use these.
# Keyed by YouTube video ID. Use "Bhartendra (solo)" for solo episodes.
GUEST_OVERRIDES = {
    # Episodes where guest is named in title but wasn't auto-extracted:
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
    'Ms_2WqYOIsY': 'Abhinav Angirish',
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
    '7RURrUgKXig': 'Bhartendra (solo)',     # Ep 27 — Home buying costs
    'ejC8nevgQb0': 'Bhartendra (solo)',     # Ep 25 — Where to invest 2025
    '7YdiFShGRRQ': 'Bhartendra (solo)',     # Ep 24 — Wealth with limited income
    'C966CXKS_tU': 'Bhartendra (solo)',     # Ep 23 — Retirement scares us
    'jCRb7WpH6h4': 'Bhartendra (solo)',     # Ep 22 — Find your number
    'o1_3k5EkzZg': 'Bhartendra (solo)',     # Ep 21 — Rupee falling
    'ch96iqz4wj8': 'Bhartendra (solo)',     # Ep 17 — 10 crore SIP (guest name not in title)
    'OlrHz1Og_kY': 'Bhartendra (solo)',     # Ep 13 — Behavioral edge / CIO (name not in title)
    '_pO65w9FnTo': 'Bhartendra (solo)',     # Ep 12 — Mutual funds truth
}

# Guest → role/title. Add to this as new guests come on the show.
GUEST_ROLES = {
    'Vijai Mantri': 'Founder, VMFS',
    'Debashish Bose': 'Founder, Infinite Circle',
    'Krishna Sharma': 'Gateway to Financial Freedom',
    'Mahmood Basha Shaik': 'Baroda BNP Paribas',
    'Kalpen Parekh': 'CEO, DSP Mutual Fund',
    'Kirtan Shah': 'Founder, Credence Wealth',
    'Neil Borate': 'Deputy Editor, Mint',
    'Karan Datta': 'CBO, Axis Mutual Fund',
    'Thomas Priju': 'Fund Manager',
    'Mohit Bhatia': 'CEO, Bank of India MF',
    'Vinayak Sapre': 'Financial Coach',
    'Chirag Barjatya': 'Founder, PFC',
    'CA Anuj Jain': 'Chartered Accountant',
    'Sneha Jain': 'Fund Manager',
    'Devina Mehra': 'Founder, First Global',
    'Pooja Bhinde': 'Financial Planner',
    'Ajit Menon': 'Investment Strategist',
    'Dhirendra Kumar': 'CEO, Value Research',
    'Lisa Pallavi Barbora': 'Financial Journalist',
    'Mahavir Chopra': 'Founder, Beshak.org',
    'Aashish Sommaiya': 'CEO, WhiteOak Capital',
    'Abhinav Angirish': 'Founder, Investonline.in',
    'Raghav Iyengar': 'CEO, Axis Mutual Fund',
    'Mrin Agarwal': 'Founder, Finsafe',
    'Niranjan Avasthi': 'Head of Product, Edelweiss MF',
    'Shaymali Basu': 'Financial Planner',
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

def parse_guest(vid, title, stats):
    if vid in GUEST_OVERRIDES:
        return GUEST_OVERRIDES[vid]
    for s in stats:
        m = re.match(r'ThisOrThat with Bhartendra and (.+?)(?:\s*-.*)?$', s)
        if m:
            return m.group(1).strip().replace('Krishan Sharma','Krishna Sharma').replace('Mahamood','Mahmood')
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
    t = title.lower()
    if any(w in t for w in ['retire','pension',' pf ','epf','insurance','health']): return 'Retirement'
    if any(w in t for w in ['gold','silver','metal']): return 'Commodities'
    if any(w in t for w in ['global',' us ','nasdaq','dollar','magnificent','abroad','india is not']): return 'Global'
    if any(w in t for w in ['real estate','house','home','rent','property','घर']): return 'Real Estate'
    if any(w in t for w in ['budget','tax','ltcg']): return 'Tax'
    if any(w in t for w in ['sip','mutual fund','fund','equity','stock']): return 'Investing'
    if any(w in t for w in ['family','couple','wealth','financial freedom','crore','rich']): return 'Wealth'
    if any(w in t for w in ['market','pe','bond','yield']): return 'Markets'
    if any(w in t for w in ['hidden','mistake','mindset','panic','simple','emotion','women','behavior','behavioral']): return 'Behaviour'
    return 'Investing'

def initials_of(name):
    if not name or 'solo' in name.lower(): return 'BS'
    parts = [p for p in re.sub(r'^CA\s+|^Mr\.?\s+', '', name).split() if p and p[0].isupper()]
    return parts[0][:2].upper() if len(parts) == 1 else (parts[0][0] + parts[-1][0]).upper()

# ─── Main ────────────────────────────────────────────────────────────────
def main():
    print(f'→ Syncing from YouTube channel {CHANNEL_HANDLE} …')
    raw = fetch_channel_videos()
    print(f'  Found {len(raw)} long-form episodes')

    episodes = []
    for i, v in enumerate(raw):
        ep_num = len(raw) - i
        episodes.append({
            'n': ep_num,
            'id': v['id'],
            'title': clean_title(v['title']),
            'guest': parse_guest(v['id'], v['title'], v['stats']),
            'cat': categorize(v['title']),
            'views': parse_views(v['stats']),
            'published': parse_published(v['stats']),
            'thumb': f'https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg',
        })

    # Build guests aggregate
    from collections import defaultdict
    guest_eps = defaultdict(list)
    for e in episodes:
        if e['guest'] and 'solo' not in e['guest'].lower():
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
    print(f'  Synced at {synced_at}')
    print()
    print('  Top guests:')
    for g in guests[:5]:
        print(f'    {g["eps"]}x  {g["name"]} ({g["role"]})')

if __name__ == '__main__':
    main()
