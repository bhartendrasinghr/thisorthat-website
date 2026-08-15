#!/usr/bin/env python3
"""
ThisOrThat with Bhartendra — site build script.

Runs on every Netlify deploy (configured in netlify.toml). Two jobs:

1. Re-pull latest episodes from YouTube → episodes.js
2. Compile content/articles/*.md → content/articles.json (for the articles
   grid + detail pages to consume at runtime)

Run locally with:   python3 build.py
"""
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).parent
ARTICLES_DIR = ROOT / 'content' / 'articles'
ARTICLES_OUT = ROOT / 'content' / 'articles.json'
GUESTS_DIR = ROOT / 'content' / 'guests'
GUESTS_OUT = ROOT / 'content' / 'guests.json'

# ─── Frontmatter + markdown parsing (no external deps) ───────────────────
def parse_frontmatter(text):
    """Extract YAML frontmatter between leading --- markers. Returns (meta_dict, body).

    Uses PyYAML when it is available. The hand rolled fallback below reads line by
    line, which silently truncated any value the CMS wrapped across lines: a long
    quote came out as its first line plus a stray quote character. The fallback now
    joins continuation lines before parsing.
    """
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
    if not m:
        return {}, text
    meta_block, body = m.group(1), m.group(2)

    try:
        import yaml
        meta = yaml.safe_load(meta_block) or {}
        if isinstance(meta, dict):
            return meta, body
    except Exception:
        pass

    # Fallback: join wrapped lines onto the key they belong to, then parse.
    joined, buf = [], None
    for line in meta_block.splitlines():
        if re.match(r'^[A-Za-z_][\w-]*\s*:', line):
            if buf is not None: joined.append(buf)
            buf = line.rstrip()
        elif buf is not None and line.strip():
            buf += ' ' + line.strip()          # a wrapped continuation of the value
    if buf is not None: joined.append(buf)

    meta = {}
    for line in joined:
        if line.startswith('#'): continue
        k, _, v = line.partition(':')
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            quote = v[0]
            v = v[1:-1]
            v = v.replace('\\' + quote, quote) if quote == '"' else v.replace(quote * 2, quote)
        if isinstance(v, str):
            if v.lower() == 'true': v = True
            elif v.lower() == 'false': v = False
            elif re.match(r'^-?\d+$', v): v = int(v)
        meta[k] = v
    return meta, body


def markdown_to_html(md):
    """Minimal markdown → HTML for the essay format we use (h2, paragraphs, blockquotes, em, bold)."""
    lines = md.split('\n')
    html_parts = []
    para = []
    in_blockquote = False
    bq_lines = []

    def flush_para():
        if para:
            joined = ' '.join(para).strip()
            if joined:
                html_parts.append(f'<p>{inline(joined)}</p>')
            para.clear()

    def flush_bq():
        nonlocal in_blockquote
        if bq_lines:
            content = ' '.join(bq_lines).strip()
            html_parts.append(f'<blockquote>{inline(content)}</blockquote>')
            bq_lines.clear()
        in_blockquote = False

    def inline(text):
        # Bold **x**
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Italic *x* or _x_
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
        # Links [text](url)
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
        return text

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('## '):
            flush_para(); flush_bq()
            html_parts.append(f'<h2>{inline(stripped[3:].strip())}</h2>')
        elif stripped.startswith('# '):
            flush_para(); flush_bq()
            html_parts.append(f'<h1>{inline(stripped[2:].strip())}</h1>')
        elif stripped.startswith('> '):
            flush_para()
            in_blockquote = True
            bq_lines.append(stripped[2:].strip())
        elif stripped.startswith('- ') or stripped.startswith('* '):
            flush_para(); flush_bq()
            # Simple list handling — collect consecutive items
            html_parts.append(f'<li>{inline(stripped[2:].strip())}</li>')
        elif re.match(r'^\d+\.\s', stripped):
            flush_para(); flush_bq()
            li_text = re.sub(r'^\d+\.\s', '', stripped)
            html_parts.append(f'<li>{inline(li_text)}</li>')
        elif stripped == '':
            flush_para(); flush_bq()
        else:
            if in_blockquote:
                bq_lines.append(stripped)
            else:
                para.append(stripped)
    flush_para(); flush_bq()

    # Wrap consecutive <li> in <ul>
    out = []
    in_list = False
    for p in html_parts:
        if p.startswith('<li>'):
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(p)
        else:
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append(p)
    if in_list: out.append('</ul>')

    return '\n'.join(out)

# ─── Build articles.json from markdown files ─────────────────────────────
def build_articles():
    if not ARTICLES_DIR.exists():
        print(f'  No articles directory at {ARTICLES_DIR}, skipping')
        return
    articles = []
    for path in sorted(ARTICLES_DIR.glob('*.md'), reverse=True):
        text = path.read_text(encoding='utf-8')
        meta, body = parse_frontmatter(text)
        if not meta.get('slug'):
            # Derive slug from filename
            stem = path.stem
            slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', stem)
            meta['slug'] = slug
        meta['body_html'] = markdown_to_html(body)
        # Excerpt = first paragraph plain text, truncated
        first_p = re.search(r'<p>(.+?)</p>', meta['body_html'])
        if first_p:
            excerpt = re.sub(r'<[^>]+>', '', first_p.group(1))
            meta['excerpt'] = excerpt[:200] + ('…' if len(excerpt) > 200 else '')
        else:
            meta['excerpt'] = ''
        # Date as ISO string for JSON
        if 'date' in meta and not isinstance(meta['date'], str):
            meta['date'] = str(meta['date'])
        articles.append(meta)

    with ARTICLES_OUT.open('w') as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
    print(f'  Compiled {len(articles)} articles → {ARTICLES_OUT.name}')

# ─── Build guests.json from markdown files ───────────────────────────────
def build_guests():
    if not GUESTS_DIR.exists():
        print(f'  No guests directory at {GUESTS_DIR}, skipping')
        return
    guests = []
    for path in sorted(GUESTS_DIR.glob('*.md')):
        text = path.read_text(encoding='utf-8')
        meta, body = parse_frontmatter(text)
        if not meta.get('slug'):
            meta['slug'] = path.stem
        if not meta.get('name'):
            print(f'  ⚠ {path.name} missing required "name" field — skipping')
            continue
        meta['bio_html'] = markdown_to_html(body) if body.strip() else ''
        # Excerpt for cards
        first_p = re.search(r'<p>(.+?)</p>', meta['bio_html'])
        if first_p:
            excerpt = re.sub(r'<[^>]+>', '', first_p.group(1))
            meta['excerpt'] = excerpt[:160] + ('…' if len(excerpt) > 160 else '')
        else:
            meta['excerpt'] = ''
        # Normalise empty photo
        if not meta.get('photo'):
            meta['photo'] = ''
        # The pages add their own quote marks, so strip any the author typed.
        q = str(meta.get('quote') or '').strip()
        if len(q) >= 2 and q[0] in '"\u201c\u2018\'' and q[-1] in '"\u201d\u2019\'':
            q = q[1:-1].strip()
        meta['quote'] = q
        guests.append(meta)

    with GUESTS_OUT.open('w') as f:
        json.dump(guests, f, indent=2, ensure_ascii=False)
    print(f'  Compiled {len(guests)} guest profiles → {GUESTS_OUT.name}')

# ─── Run YouTube sync ────────────────────────────────────────────────────
def sync_youtube():
    sync_path = ROOT / 'sync.py'
    if sync_path.exists():
        print('→ Syncing YouTube channel...')
        import subprocess
        result = subprocess.run([sys.executable, str(sync_path)], capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(f'  sync.py failed (continuing): {result.stderr[:200]}', file=sys.stderr)
    else:
        print('  sync.py not found, skipping YouTube sync')

def build_stats():
    """Count the live tools and stamp the number wherever it is displayed.
    Runs every deploy, so adding or removing a calc-*.html updates all counts."""
    import re as _re, json as _json
    calcs = sorted(ROOT.glob('calc-*.html'))
    tools = len(calcs) + (1 if (ROOT / 'asset-allocator.html').exists() else 0)
    ncalc = len(calcs) - (1 if (ROOT / 'calc-plan.html').exists() else 0)
    # about.html stat tile: total interactive tools
    ab = ROOT / 'about.html'
    t = ab.read_text(encoding='utf-8')
    t2 = _re.sub(r"(\[data-stat-calcs\]'\)\.forEach\(el => el\.textContent = ')\d+(')",
                 lambda m: m.group(1) + str(tools) + m.group(2), t)
    if t2 != t: ab.write_text(t2, encoding='utf-8')
    # calculators.html badge + meta: "planner, allocator + N calculators"
    ch = ROOT / 'calculators.html'
    c = ch.read_text(encoding='utf-8')
    c2 = _re.sub(r'allocator \+ \d+ calculators', f'allocator + {ncalc} calculators', c)
    # MF category count, read from the data array so the hub card can never go stale
    mf = ROOT / 'understanding-mutual-funds.html'
    nmf = 0
    if mf.exists():
        m = _re.search(r'const CATS = (\[.*?\]);\n', mf.read_text(encoding='utf-8'), _re.S)
        if m:
            nmf = len(_json.loads(m.group(1)))
            c2 = _re.sub(r'(All <span class="font-mono tab-num">)\d+(</span> SEBI categories)',
                         lambda x: x.group(1) + str(nmf) + x.group(2), c2)
    if c2 != c: ch.write_text(c2, encoding='utf-8')
    print(f'  Stats: {tools} tools live ({ncalc} calculators + planner + allocator), {nmf} MF categories')

def build_sitemap():
    """Generate sitemap.xml (core pages + every episode URL) and robots.txt."""
    import re as _re, json as _json, datetime as _dt
    site = 'https://thisorthatshow.in'
    skip = {'404.html', 'admin'}
    core = sorted(p.name for p in ROOT.glob('*.html')
                  if p.name not in skip and not p.name.endswith('-mock.html'))
    urls = [f'{site}/' if p == 'index.html' else f'{site}/{p}' for p in core]
    eps_path = ROOT / 'episodes.js'
    if eps_path.exists():
        m = _re.search(r'window\.EPISODES\s*=\s*(\[.*?\]);', eps_path.read_text(encoding='utf-8'), _re.S)
        if m:
            for e in _json.loads(m.group(1)):
                urls.append(f'{site}/episode-detail.html?v={e["id"]}')
    today = _dt.date.today().isoformat()
    entries = '\n'.join(
        f'  <url><loc>{u.replace("&", "&amp;")}</loc><lastmod>{today}</lastmod></url>' for u in urls)
    (ROOT / 'sitemap.xml').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{entries}\n</urlset>\n', encoding='utf-8')
    (ROOT / 'robots.txt').write_text(
        f'User-agent: *\nAllow: /\nDisallow: /admin/\n\nSitemap: {site}/sitemap.xml\n', encoding='utf-8')
    print(f'  Wrote sitemap.xml ({len(urls)} URLs) + robots.txt')

def check_redirects():
    """Every page needs an extensionless redirect in vercel.json, or /about style
    URLs 404. Vercel reads vercel.json before the build, so this can only warn:
    add the entry by hand, then redeploy."""
    import json as _json
    cfg_path = ROOT / 'vercel.json'
    if not cfg_path.exists():
        return
    cfg = _json.loads(cfg_path.read_text(encoding='utf-8'))
    have = {r['source'].lstrip('/') for r in cfg.get('redirects', [])}
    # mocks are noindex drafts and are deliberately not given a pretty URL
    skip = {'404'} | {p.stem for p in ROOT.glob('*-mock.html')}
    missing = sorted(p.stem for p in ROOT.glob('*.html') if p.stem not in skip and p.stem not in have)
    if missing:
        print('  ⚠ No extensionless redirect for: ' + ', '.join(missing))
        print('    Add {"source":"/NAME","destination":"/NAME.html","permanent":false} to vercel.json')
    else:
        print(f'  All {len(have)} page redirects present')



# ─── Make the Episode Overrides screen readable ──────────────────────────
# It listed rows as bare 11-character video IDs, which nobody can recognise.
# Every episode now gets a row, labelled and ordered newest first, so the
# screen is something you can scan instead of decode. The label is written
# here on every build, so it is never something to maintain by hand.
def label_episode_overrides():
    import json as _json
    epf = ROOT / 'episodes.js'
    ovf = ROOT / 'content' / 'episode-overrides.json'
    if not (epf.exists() and ovf.exists()):
        return
    raw = epf.read_text(encoding='utf-8')
    m = re.search(r'window\.EPISODES\s*=\s*(\[.*?\]);', raw, re.S)
    if not m:
        return
    eps = _json.loads(m.group(1))
    by_id = {e['id']: e for e in eps}

    cfg = _json.loads(ovf.read_text(encoding='utf-8'))
    rows = {o['video_id']: o for o in cfg.get('overrides', [])}

    out = []
    for e in sorted(eps, key=lambda x: -x['n']):
        row = rows.pop(e['id'], {'video_id': e['id'], 'guest': '', 'category': '', 'title': ''})
        row['episode'] = f"EP {e['n']:03d}  ·  {e['title'][:70]}"
        row.setdefault('guest', ''); row.setdefault('category', ''); row.setdefault('title', '')
        out.append({k: row.get(k, '') for k in ('episode', 'video_id', 'guest', 'category', 'title')})
    # anything overridden for a video the sync no longer returns, kept not dropped
    for vid, row in rows.items():
        row['episode'] = f"(not in the current feed)  ·  {vid}"
        out.append({k: row.get(k, '') for k in ('episode', 'video_id', 'guest', 'category', 'title')})

    cfg['overrides'] = out
    ovf.write_text(_json.dumps(cfg, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'  Labelled {len(out)} override rows, newest first')

# ─── One menu, everywhere ────────────────────────────────────────────────
# The site had drifted into three different menus: 21 pages with Feed,
# 11 without it, and the home page with its own. Each page kept its own
# copy, so every new page inherited whichever version was copied. The nav
# is now generated here and written into every page on each build, so it
# cannot drift again. Page styling is left alone; only the links change.
NAV_ITEMS = [
    ('episodes.html',    'Episodes'),
    ('guests.html',      'Guests'),
    ('calculators.html', 'Plan'),
    ('articles.html',    'Writing'),
    ('about.html',       'About'),
]

def sync_nav():
    import re
    skip = {'404.html'}   # brand.html and 404 have no nav; detail pages do and need it too
    changed = 0
    for path in sorted(ROOT.glob('*.html')):
        if path.name in skip or path.name.endswith('-mock.html'):
            continue
        s = path.read_text(encoding='utf-8')
        head = re.search(r'<header[^>]*>.*?</header>', s, re.S)
        if not head:
            continue
        block = head.group(0)

        # desktop nav: keep the page's own classes, replace only the links
        nav = re.search(r'(<nav\b[^>]*>)(.*?)(</nav>)', block, re.S)
        if not nav:
            continue
        link_cls = re.search(r'<a\b[^>]*class="([^"]*)"', nav.group(2))
        link_cls = link_cls.group(1) if link_cls else ''
        active_cls = link_cls
        parts = []
        for h, t in NAV_ITEMS:
            here = ' aria-current="page"' if h == path.name else ''
            parts.append('<a href="%s" class="%s"%s>%s</a>' % (h, link_cls, here, t))
        links = ''.join(parts)
        new_block = block.replace(nav.group(0), nav.group(1) + links + nav.group(3))

        # mobile menu, whichever id this page uses
        mob = re.search(r'(<div id="(?:mobile-menu|mm)"[^>]*>\s*<nav\b[^>]*>)(.*?)(</nav>)', s, re.S)
        new_s = s.replace(block, new_block)
        if mob:
            mcls = re.search(r'<a\b[^>]*class="([^"]*)"', mob.group(2))
            mcls = mcls.group(1) if mcls else ''
            mlinks = ''.join(f'<a href="{h}" class="{mcls}">{t}</a>' for h, t in NAV_ITEMS)
            new_s = new_s.replace(mob.group(0), mob.group(1) + mlinks + mob.group(3))

        if new_s != s:
            path.write_text(new_s, encoding='utf-8')
            changed += 1
    print(f'  Synced the menu into {changed} pages: ' + ' · '.join(t for _, t in NAV_ITEMS))

# ─── Main ────────────────────────────────────────────────────────────────
def main():
    print('=== ThisOrThat build ===')
    print()
    print('→ Compiling articles...')
    build_articles()
    print()
    print('→ Compiling guest profiles...')
    build_guests()
    print()
    # YouTube sync can fail in CI if network is blocked — make optional
    if os.environ.get('SKIP_YT_SYNC') != '1':
        sync_youtube()
    print()
    print('→ Updating tool counts...')
    build_stats()
    print()
    print('\n→ Labelling episode overrides for the CMS...')
    label_episode_overrides()

    print('\n→ Syncing the menu across pages...')
    sync_nav()

    print('→ Generating sitemap + robots...')
    build_sitemap()
    print()
    print('→ Checking page redirects...')
    check_redirects()
    print()
    print('✓ Build complete')

if __name__ == '__main__':
    main()
