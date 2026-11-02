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
import re as _re_module

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
        # Trailing spaces get typed into the CMS and then render as gaps.
        for k in ('name', 'role', 'slug'):
            if isinstance(meta.get(k), str):
                meta[k] = meta[k].strip()
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
            # Loud on purpose. This failing quietly is how the site served
            # three week old episodes while every deploy reported success.
            print('  ' + '!' * 68, file=sys.stderr)
            print('  YOUTUBE SYNC FAILED. episodes.js is whatever was last committed.', file=sys.stderr)
            print('  The deploy will still succeed. The episode list will be stale.', file=sys.stderr)
            print('  Expected on Vercel: YouTube blocks the scrape from datacenter IPs.', file=sys.stderr)
            print('  The fix is the sync-episodes GitHub Action, which commits the', file=sys.stderr)
            print('  refreshed file from a different network.', file=sys.stderr)
            print(f'  {result.stderr[:300]}', file=sys.stderr)
            print('  ' + '!' * 68, file=sys.stderr)
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
    # episode-detail.html is the shell behind the real episode pages and
    # redirects to them, so it is not a URL to offer. brand.html is the
    # internal brand guide; it is served noindex and does not belong here.
    skip = {'404.html', 'admin', 'brand.html', 'episode-detail.html',
            'article-detail.html', 'guest-detail.html'}
    core = sorted(p.name for p in ROOT.glob('*.html')
                  if p.name not in skip and not p.name.endswith('-mock.html'))
    urls = [f'{site}/' if p == 'index.html' else f'{site}/{p}' for p in core]
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
    # Episode pages are covered by the single /ep-:slug wildcard rule.
    skip = ({'404'} | {p.stem for p in ROOT.glob('*-mock.html')}
            | {p.stem for p in ROOT.glob('ep-[0-9][0-9][0-9]-*.html')})
    missing = sorted(p.stem for p in ROOT.glob('*.html') if p.stem not in skip and p.stem not in have)
    if missing:
        print('  ⚠ No extensionless redirect for: ' + ', '.join(missing))
        print('    Add {"source":"/NAME","destination":"/NAME.html","permanent":false} to vercel.json')
    else:
        print(f'  All {len(have)} page redirects present')



# ─── Head tags every page needs ──────────────────────────────────────────
# Two things were being added by hand and so were missing from most pages:
# a canonical URL (34 of 46 had none) and the analytics tag (no page had one,
# which meant nothing about this site was measured at all). Both are
# mechanical, so neither should be anybody's job to remember.
# The tag itself, inline, because Google wants it as high in <head> as it
# will go and because the automatic page_view fires from this block, before
# any external file has loaded. Two things ride along with it:
#
#   page_type   so every hit can be read by section rather than by URL. It
#               has to be worked out here, for the reason above: a page_type
#               set later would miss the page_view it is meant to label.
#   analytics.js  deferred, carrying every custom event. A blocked or slow
#               analytics.js costs us the detail and never the page.
#
# This string is the single source of truth and is replaced wholesale on
# every build (see GA_BLOCK_RE), so editing it here updates all 115 pages.
ANALYTICS_TAG = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-QDF1DKH66W"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  window.TOT_PAGE_TYPE = (function (p) { return (
    !p || p == 'index' ? 'home' :
    /^ep-\d/.test(p) ? 'episode' :
    /^calc-|^(asset-allocator|funds|category-compass|ipo-checker)$/.test(p) ? 'tool' :
    p == 'calculators' ? 'tool_index' :
    /^(episodes|episode-detail)$/.test(p) ? 'episode_index' :
    p == 'guests' ? 'guest_index' :
    p == 'guest-detail' ? 'guest' :
    p == 'articles' ? 'article_index' :
    p == 'article-detail' ? 'article' :
    /-pulse$/.test(p) ? 'pulse' :
    /^(asset-classes|understanding-mutual-funds|ways-to-invest-in-equity|wealth-levers|multicap-vs-flexicap)$/.test(p) ? 'guide' :
    p == 'money-person' ? 'lead' :
    p == 'ipo-tracker' ? 'data' :
    /^(privacy|terms)$/.test(p) ? 'legal' :
    p == '404' ? 'not_found' :
    /-mock$|^brand$/.test(p) ? 'internal' : 'page'); })(
    location.pathname.replace(/^\/+/, '').replace(/\.html$/, ''));
  gtag('js', new Date());
  gtag('config', 'G-QDF1DKH66W', {
    page_type: window.TOT_PAGE_TYPE,
    /* privacy.html says this is used to understand pages, not people.
       These two keep that true: no Google Signals, no ad personalisation. */
    allow_google_signals: false,
    allow_ad_personalization_signals: false
  });
</script>
<script src="/analytics.js" defer></script>"""

# Everything from the comment marker through the config block, and the
# analytics.js line if it is already there. Matching the whole block rather
# than a fixed string is what makes the step idempotent: the tag can be
# edited above and the next build rewrites every page to match.
GA_BLOCK_RE = _re_module.compile(
    r'<!-- Google tag \(gtag\.js\) -->\s*'
    r'<script async src="https://www\.googletagmanager\.com/gtag/js\?id=G-QDF1DKH66W"></script>\s*'
    r'<script>.*?</script>'
    r'(?:\s*<script src="/analytics\.js" defer></script>)?',
    _re_module.S)

# What was here before. Vercel Web Analytics was never switched on in the
# project, so this tag only ever 404'd, on every page load. Left in place it
# would be a dead request next to a live one.
OLD_ANALYTICS_TAG = '<script defer src="/_vercel/insights/script.js"></script>'


def sync_head_tags():
    import re as _re
    site = 'https://thisorthatshow.in'
    # Shells and drafts: a canonical pointing at a page that renders nothing
    # useful is worse than none. episode-detail.html sets its own in JS, to
    # the real episode page it redirects to.
    no_canonical = {'404.html', 'episode-detail.html', 'article-detail.html',
                    'guest-detail.html', 'brand.html'}
    added_c = added_a = moved_a = 0
    # brand.html is the internal brand guide, served noindex: it is not part
    # of the public site and is 3 MB, so it stays out of this entirely.
    for f in sorted(ROOT.glob('*.html')):
        if f.name.endswith('-mock.html') or f.name == 'brand.html':
            continue
        h = f.read_text(encoding='utf-8')
        before = h

        if 'rel="canonical"' not in h and f.name not in no_canonical:
            url = f'{site}/' if f.name == 'index.html' else f'{site}/{f.name}'
            m = _re.search(r'</title>', h)
            if m:
                h = (h[:m.end()] + f'\n<link rel="canonical" href="{url}" />'
                     + h[m.end():])
                added_c += 1

        # Migrate: the Vercel tag never had anything behind it.
        if OLD_ANALYTICS_TAG in h:
            h = h.replace(OLD_ANALYTICS_TAG + '\n', '').replace(OLD_ANALYTICS_TAG, '')
        # Google asks for the tag as high in <head> as it will go, and exactly
        # once. Charset has to stay inside the first 1024 bytes and viewport
        # belongs beside it, so the tag goes immediately after those two and
        # ahead of everything else: title, fonts, Tailwind, the lot.
        #
        # A page that already carries a tag has the whole block rewritten
        # rather than left alone, so ANALYTICS_TAG above stays the one place
        # the tag is defined. Without this, editing the tag would silently
        # apply to new pages only and the site would drift apart.
        if GA_BLOCK_RE.search(h):
            rewritten = GA_BLOCK_RE.sub(lambda m: ANALYTICS_TAG, h, count=1)
            if rewritten != h:
                h = rewritten
                moved_a += 1
        else:
            anchor = _re.search(
                r'<head[^>]*>\s*(?:<meta[^>]*charset[^>]*>\s*)?'
                r'(?:<meta[^>]*name="viewport"[^>]*>\s*)?', h, _re.I)
            if anchor:
                h = h[:anchor.end()] + ANALYTICS_TAG + '\n' + h[anchor.end():]
                added_a += 1
        # A second tag on one page double-counts every view, which is the one
        # analytics bug that is invisible until someone compares totals.
        if h.count('gtag/js?id=G-QDF1DKH66W') > 1:
            raise SystemExit(f'{f.name} carries the Google tag twice')

        if h != before:
            f.write_text(h, encoding='utf-8')
    print(f'  {added_c} canonical tag(s) added, {added_a} analytics tag(s) added, '
          f'{moved_a} refreshed to the current tag')


# ─── Is the measurement actually on every page ───────────────────────────
# The failure mode for analytics is silence: a page that quietly stopped
# reporting looks exactly like a page nobody visited, and you find out weeks
# later when you go looking for a number that was never collected. So the
# build asserts it rather than hoping.
def check_analytics():
    missing_tag, missing_js, drifted, twice = [], [], [], []
    for f in sorted(ROOT.glob('*.html')):
        if f.name.endswith('-mock.html') or f.name == 'brand.html':
            continue
        h = f.read_text(encoding='utf-8')
        loaders = h.count('gtag/js?id=G-QDF1DKH66W')
        if loaders == 0:
            missing_tag.append(f.name)
            continue
        if loaders > 1:
            twice.append(f.name)
        if '<script src="/analytics.js" defer></script>' not in h:
            missing_js.append(f.name)
        if ANALYTICS_TAG not in h:
            drifted.append(f.name)

    js = ROOT / 'analytics.js'
    if not js.exists() or js.stat().st_size < 2000:
        raise SystemExit('analytics.js is missing or truncated')

    for label, pages in (('no Google tag', missing_tag),
                         ('two Google tags', twice),
                         ('no analytics.js', missing_js),
                         ('an out-of-date tag', drifted)):
        if pages:
            raise SystemExit(f'  {len(pages)} page(s) with {label}: '
                             + ', '.join(pages[:6]))
    print('  every public page: one tag, current, with the event layer')


# ─── The shared tool layer ───────────────────────────────────────────────
# tools.css and tools.js carry what should be true of every calculator:
# grabbable sliders, state in the URL, state remembered, a share button and
# the sticky answer bar. Wiring is done here rather than by hand so a new
# calculator cannot quietly ship without them.
TOOL_PAGES_GLOB = ('calc-*.html', 'asset-allocator.html', 'money-person.html')

def sync_tool_assets():
    pages = []
    for g in TOOL_PAGES_GLOB:
        pages.extend(sorted(ROOT.glob(g)))
    css_added = js_added = 0
    for f in pages:
        h = f.read_text(encoding='utf-8')
        before = h
        # Last in <head>, so it wins ties with the page's own inline <style>.
        if 'tools.css' not in h and '</head>' in h:
            h = h.replace('</head>', '<link rel="stylesheet" href="tools.css" />\n</head>', 1)
            css_added += 1
        # After the page's own script, which has already run its first calc().
        if 'tools.js' not in h and ANALYTICS_TAG in h:
            h = h.replace(ANALYTICS_TAG, '<script src="tools.js"></script>\n' + ANALYTICS_TAG, 1)
            js_added += 1
        elif 'tools.js' not in h and '</body>' in h:
            h = h.replace('</body>', '<script src="tools.js"></script>\n</body>', 1)
            js_added += 1
        if h != before:
            f.write_text(h, encoding='utf-8')
    print(f'  {len(pages)} tool pages: {css_added} got tools.css, {js_added} got tools.js')


# ─── Somewhere to put an email address ───────────────────────────────────
# The newsletter block promised "Slow Thought, weekly. One honest idea.
# Every week." on 78 pages and then offered a Subscribe on YouTube button
# underneath it. The promise and the payload did not match, and there was no
# way at all to subscribe to the thing being described: every path off this
# site led to a platform Bhartendra does not own. This swaps the button for
# a real form posting to /api/subscribe, and keeps YouTube as the second
# option rather than the only one.
OLD_CTA = ('<a href="https://www.youtube.com/@ThisOrThatPodcastIndia?sub_confirmation=1" '
           'target="_blank" class="mt-6 inline-flex bg-navy text-cream px-7 py-3 '
           'rounded-full font-semibold hover:bg-navy-ink transition">Subscribe on YouTube &rarr;</a>')

SUBSCRIBE_FORM = """<form class="nl-form mt-6 flex flex-col sm:flex-row gap-3 justify-center max-w-lg mx-auto" novalidate>
      <label class="sr-only" for="nl-email">Your email address</label>
      <input id="nl-email" name="email" type="email" required autocomplete="email"
             placeholder="you@example.com"
             class="flex-1 min-h-[48px] px-5 py-3 rounded-full border-2 border-ink/20 bg-warmpaper text-ink placeholder-ink/40 focus:border-ink focus:outline-none" />
      <input type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true" class="hidden" />
      <button type="submit" class="nl-submit min-h-[48px] bg-navy text-cream px-7 py-3 rounded-full font-semibold hover:bg-navy-ink transition shrink-0">Send it to me</button>
    </form>
    <p class="nl-note mt-3 text-[13px] text-ink/70" role="status" aria-live="polite">One email a week. No spam, and you can leave whenever you like.</p>
    <p class="mt-4 text-[13px]"><a href="https://www.youtube.com/@ThisOrThatPodcastIndia?sub_confirmation=1" target="_blank" class="underline underline-offset-4 font-semibold">Or subscribe on YouTube &rarr;</a></p>"""

# A regex rather than a fixed string, so that editing SUBSCRIBE_JS below
# rewrites the block on all 80 pages that carry it instead of only reaching
# pages that have never had it. The markers make the boundary explicit; the
# unmarked opening is kept so the first build after this change still finds
# the version already on the pages.
NL_JS_RE = _re_module.compile(
    r'(?:<!-- NL-JS -->\s*)?<script>\s*//\s*Newsletter signup\..*?</script>'
    r'(?:\s*<!-- /NL-JS -->)?',
    _re_module.S)

SUBSCRIBE_JS = """<!-- NL-JS -->
<script>
// Newsletter signup. Posts with fetch and answers in place, rather than
// navigating the reader away from whatever they were in the middle of.
//
// The analytics calls are guarded rather than assumed: this form has to keep
// working on a page where analytics.js was blocked, which is most of the
// reason the outcome is reported from here at all. Only the outcome and the
// page are recorded. The address is not.
document.querySelectorAll('.nl-form').forEach(function (form) {
  var ga = function (name, params) {
    if (typeof window.totTrack === 'function') window.totTrack(name, params || {});
  };
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var email = form.querySelector('input[name=email]');
    var btn = form.querySelector('.nl-submit');
    var note = form.parentNode.querySelector('.nl-note');
    var say = function (m) { if (note) note.textContent = m; };
    var value = (email.value || '').trim();
    if (value.indexOf('@') < 1 || value.indexOf('.') < 0) {
      say('That address looks incomplete, have another look.');
      ga('newsletter_error', { reason: 'malformed' });
      email.focus(); return;
    }
    ga('newsletter_submit');
    btn.disabled = true; btn.textContent = 'Sending...';
    fetch('/api/subscribe', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        email: value,
        page: location.pathname.replace(/^\\//, '').replace(/\\.html$/, '') || 'home',
        website: form.querySelector('input[name=website]').value
      })
    }).then(function (r) { return r.json().catch(function () { return { ok: r.ok }; }); })
      .then(function (d) {
        if (d && d.ok) {
          form.innerHTML = '<p class="font-semibold text-ink py-3">You are on the list. Look out for the first one.</p>';
          say('');
          ga('newsletter_signup');
        } else {
          btn.disabled = false; btn.textContent = 'Send it to me';
          say(d && d.error === 'email'
            ? 'That address looks incomplete, have another look.'
            : 'That did not go through. Try again in a moment.');
          ga('newsletter_error', { reason: (d && d.error) || 'rejected' });
        }
      }).catch(function () {
        btn.disabled = false; btn.textContent = 'Send it to me';
        say('That did not go through. Try again in a moment.');
        ga('newsletter_error', { reason: 'network' });
      });
  });
});
</script>
<!-- /NL-JS -->"""


def sync_newsletter():
    changed = 0
    for f in sorted(ROOT.glob('*.html')):
        if f.name.endswith('-mock.html'):
            continue
        h = f.read_text(encoding='utf-8')
        before = h
        if OLD_CTA in h:
            h = h.replace(OLD_CTA, SUBSCRIBE_FORM)
        if 'nl-form' in h and 'nl-submit' in h:
            if NL_JS_RE.search(h):
                h = NL_JS_RE.sub(lambda m: SUBSCRIBE_JS, h, count=1)
            elif '</body>' in h:
                h = h.replace('</body>', SUBSCRIBE_JS + '\n</body>', 1)
        if h != before:
            f.write_text(h, encoding='utf-8')
            changed += 1
    print(f'  {changed} page(s) now offer a real signup, not only a YouTube button')


# ─── Stop shipping the Tailwind compiler to every reader ─────────────────
# Every page loaded cdn.tailwindcss.com, which is the Play CDN: a development
# build that downloads ~120 KB of gzipped JavaScript and then generates the
# stylesheet in the browser, on every visit. Tailwind's own docs say not to
# use it in production. It also means the page paints unstyled first, which
# on an Indian 4G connection is a visible flash on every navigation.
#
# tw.css is the same utilities, built once at deploy time from
# tailwind.config.js: 53 KB raw, about 10 KB gzipped, and no runtime work.
#
# Placement matters. The CDN appended its <style> at the end of <head>, so
# its utilities beat each page's inline <style>. The link goes after that
# inline <style> for the same reason, and before tools.css, which is meant
# to have the last word.
CDN_SCRIPT = '<script src="https://cdn.tailwindcss.com"></script>'
TW_LINK = '<link rel="stylesheet" href="/tw.css" />'
TOOLS_LINK = '<link rel="stylesheet" href="tools.css" />'


def sync_tailwind():
    import re as _re
    # The inline `tailwind.config = {...}` block each page carried for the
    # CDN to read. tailwind.config.js replaces all twelve of them, and left
    # behind this would throw a ReferenceError on every page, since nothing
    # defines `tailwind` any more.
    cfg_block = _re.compile(
        r'[ \t]*<script>\s*\n?\s*tailwind\.config\s*=\s*\{.*?\};?\s*\n?\s*</script>\n?',
        _re.S)

    swapped = 0
    for f in sorted(ROOT.glob('*.html')):
        if f.name == 'brand.html':
            continue
        h = f.read_text(encoding='utf-8')
        before = h
        h = h.replace(CDN_SCRIPT + '\n', '').replace(CDN_SCRIPT, '')
        h = cfg_block.sub('', h)
        if TW_LINK not in h:
            if TOOLS_LINK in h:
                h = h.replace(TOOLS_LINK, TW_LINK + '\n' + TOOLS_LINK, 1)
            elif '</head>' in h:
                h = h.replace('</head>', TW_LINK + '\n</head>', 1)
        if h != before:
            f.write_text(h, encoding='utf-8')
            swapped += 1

    leftover = [f.name for f in ROOT.glob('*.html')
                if 'cdn.tailwindcss.com' in f.read_text(encoding='utf-8')
                and f.name != 'brand.html']
    if leftover:
        print('  WARNING: still on the CDN: ' + ', '.join(leftover[:6]))
    print(f'  {swapped} page(s) moved from the Tailwind CDN to the built tw.css')


# ─── One fonts URL, so the cache actually works ──────────────────────────
# There were six different Google Fonts URLs across the site, each asking
# for a slightly different set of weights. A different URL is a different
# cache entry, so going from the homepage to a calculator refetched the
# stylesheet and the faces it names, roughly 140 KB that the browser already
# had. One URL for every page means one entry, fetched once.
#
# It is the union of all six, verified against Google: 61 faces covering
# Bricolage Grotesque 400/700/800, Caveat 400/600/700, Hanken Grotesk
# 400-800 and IBM Plex Mono 400-700. Naming a family costs nothing on a page
# that never uses it, because the browser only downloads a face when some
# text is actually set in it.
FONTS_URL = ('https://fonts.googleapis.com/css2'
             '?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,700;12..96,800'
             '&family=Caveat:wght@400;600;700'
             '&family=Hanken+Grotesk:wght@400;500;600;700;800'
             '&family=IBM+Plex+Mono:wght@400;500;600;700'
             '&display=swap')


def sync_fonts():
    import re as _re
    link = f'<link href="{FONTS_URL}" rel="stylesheet" />'
    pre = ('<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
           '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />')
    changed = 0
    for f in sorted(ROOT.glob('*.html')):
        if f.name == 'brand.html':
            continue
        h = f.read_text(encoding='utf-8')
        before = h
        # Collapse however many font <link>s a page has into exactly one.
        links = _re.findall(
            r'[ \t]*<link[^>]*href="https://fonts\.googleapis\.com/css2[^"]*"[^>]*>\n?', h)
        if links:
            h = h.replace(links[0], link + '\n', 1)
            for extra in links[1:]:
                h = h.replace(extra, '', 1)
        # Both preconnects, so the handshake to gstatic starts before the CSS
        # has even been parsed.
        if 'fonts.gstatic.com' not in h and link in h:
            h = h.replace(link, pre + '\n' + link, 1)
        if h != before:
            f.write_text(h, encoding='utf-8')
            changed += 1
    stragglers = set()
    for f in ROOT.glob('*.html'):
        if f.name == 'brand.html':
            continue
        for u in _re.findall(r'https://fonts\.googleapis\.com/css2\?[^"]+',
                             f.read_text(encoding='utf-8')):
            if u != FONTS_URL:
                stragglers.add(u[:60])
    if stragglers:
        print('  WARNING: other font URLs remain: ' + '; '.join(sorted(stragglers)))
    print(f'  {changed} page(s) now share one fonts URL')


# ─── Structured data, on more than two pages ─────────────────────────────
# Two of forty-six pages carried any. A podcast with 74 episodes and
# seventeen free tools was telling search engines nothing about what it is,
# which is the difference between a blue link and a result with the tool's
# name, rating-free "Free" badge and breadcrumb trail attached.
#
# Episode pages build their own richer graph in build/episode_pages.py and
# are left alone here. Everything else gets: the publisher, a breadcrumb,
# and, for a calculator, a WebApplication describing what it does.
SCHEMA_MARK = 'id="site-schema"'

PUBLISHER = {
    '@type': 'Organization',
    '@id': 'https://thisorthatshow.in/#org',
    'name': 'This or That with Bhartendra',
    'url': 'https://thisorthatshow.in',
    'logo': {'@type': 'ImageObject', 'url': 'https://thisorthatshow.in/logo.png'},
    'sameAs': ['https://www.youtube.com/@ThisOrThatPodcastIndia',
               'https://instagram.com/officialthisorthat'],
}

# section label -> the hub it sits under, for the breadcrumb middle step
SECTION = {
    'calc-': ('Plan', 'calculators.html'),
    'asset-allocator': ('Plan', 'calculators.html'),
    'money-person': ('Plan', 'calculators.html'),
    'calculators': (None, None),
    'episodes': (None, None),
    'guests': (None, None),
    'articles': (None, None),
    'market-pulse': (None, None),
    'mf-pulse': ('Pulse', 'market-pulse.html'),
}

# Pages that are tools rather than reading: these get WebApplication.
TOOL_PREFIXES = ('calc-',)
TOOL_EXTRA = {'asset-allocator.html', 'money-person.html', 'ipo-checker.html',
              'funds.html', 'category-compass.html'}


def sync_schema():
    import re as _re, json as _json
    site = 'https://thisorthatshow.in'
    skip = {'brand.html', '404.html', 'episode-detail.html'}
    n = 0
    for f in sorted(ROOT.glob('*.html')):
        if (f.name in skip or f.name.endswith('-mock.html')
                or _re.match(r'^ep-\d{3}-', f.name)):
            continue
        h = f.read_text(encoding='utf-8')
        if SCHEMA_MARK in h:
            continue

        tm = _re.search(r'<title>(.*?)</title>', h, _re.S)
        dm = _re.search(r'<meta name="description"[^>]*content="([^"]*)"', h)
        title = (tm.group(1).strip() if tm else f.stem).replace('&amp;', '&')
        desc = (dm.group(1).strip() if dm else '')
        url = f'{site}/' if f.name == 'index.html' else f'{site}/{f.name}'

        graph = [PUBLISHER]

        if f.name == 'index.html':
            graph.append({
                '@type': 'WebSite', '@id': f'{site}/#website', 'url': site,
                'name': 'This or That with Bhartendra',
                'description': desc,
                'inLanguage': 'en-IN',
                'publisher': {'@id': f'{site}/#org'},
            })
        else:
            crumbs = [{'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': site}]
            label, hub = (None, None)
            for pre, v in SECTION.items():
                if f.name.startswith(pre):
                    label, hub = v
                    break
            if label and hub and hub != f.name:
                crumbs.append({'@type': 'ListItem', 'position': 2,
                               'name': label, 'item': f'{site}/{hub}'})
            # The page's own name, without the brand tail the <title> carries.
            own = _re.split(r'\s*[,|·]\s*ThisOrThat', title)[0].strip() or title
            crumbs.append({'@type': 'ListItem', 'position': len(crumbs) + 1,
                           'name': own, 'item': url})
            graph.append({'@type': 'BreadcrumbList', 'itemListElement': crumbs})

            is_tool = f.name.startswith(TOOL_PREFIXES) or f.name in TOOL_EXTRA
            if is_tool:
                graph.append({
                    '@type': 'WebApplication',
                    'name': own,
                    'url': url,
                    'description': desc,
                    'applicationCategory': 'FinanceApplication',
                    'operatingSystem': 'Any',
                    'browserRequirements': 'Requires JavaScript',
                    'inLanguage': 'en-IN',
                    'isAccessibleForFree': True,
                    # Free and no account, which is the whole pitch of these.
                    'offers': {'@type': 'Offer', 'price': '0',
                               'priceCurrency': 'INR'},
                    'publisher': {'@id': f'{site}/#org'},
                })

        blob = _json.dumps({'@context': 'https://schema.org', '@graph': graph},
                           ensure_ascii=False, separators=(',', ':'))
        blob = blob.replace('</', '<\\/')          # never close the tag early
        tag = f'<script type="application/ld+json" {SCHEMA_MARK}>{blob}</script>'
        if '</head>' not in h:
            continue
        f.write_text(h.replace('</head>', tag + '\n</head>', 1), encoding='utf-8')
        n += 1
    print(f'  {n} page(s) given structured data')


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
    ('episodes.html',     'Episodes'),
    ('guests.html',       'Guests'),
    ('market-pulse.html', 'Pulse'),
    ('calculators.html',  'Plan'),
    ('funds.html',        'Funds'),
    ('articles.html',     'Writing'),
    ('about.html',        'About'),
]

# Pages that sit under a menu item without being it. Pulse is two views of the
# same section, Market Pulse and MF Industry Pulse, switched inside the page,
# so the menu should still look lit on the second one.
NAV_ALIASES = {'mf-pulse.html': 'market-pulse.html'}

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
            mine = NAV_ALIASES.get(path.name, path.name)
            here = ' aria-current="page"' if h == mine else ''
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
    print('\n→ Refreshing the fund index from AMFI...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('fund_index', ROOT / 'build' / 'fund_index.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.build()
    except Exception as _e:
        print(f'  Fund index step skipped: {_e}')

    # Market Pulse: only the computed tiles. Wrapped, because a page that is a
    # month stale is a smaller problem than a build that will not run.
    print('\n→ Refreshing the computable half of Market Pulse...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('mp', ROOT / 'build' / 'market_pulse_refresh.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.main()
    except SystemExit as _e:
        print(f'  Market Pulse step stopped: {_e}')
    except Exception as _e:
        print(f'  Market Pulse step skipped: {_e}')

    # Category Compass: same NSE archive, same rule. If NSE is down, the last
    # category-compass.json stays, carrying its own as-of date.
    print('\n→ Scoring equity categories for Category Compass...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('cc', ROOT / 'build' / 'category_compass.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.main()
    except Exception as _e:
        print(f'  Category Compass step skipped: {_e}')

    # MF Industry Pulse: the AMFI half. Needs xlrd and pypdf, which Vercel does
    # not have, so this step is expected to skip there. The GitHub Action runs
    # it properly and commits the result, which is what the page actually reads.
    print('\n→ Reading the month out of AMFI for MF Industry Pulse...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('mfp', ROOT / 'build' / 'mf_pulse_refresh.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.main()
    except SystemExit as _e:
        print(f'  MF Pulse step stopped: {_e}')
    except Exception as _e:
        print(f'  MF Pulse step skipped: {_e}')

    # The long run of months behind the charts. Append only, and capped at a
    # couple of months per build: the bootstrap was done by hand, and after
    # that there is one new row a month. If AMFI is unreachable the committed
    # history simply stands, which is the right failure.
    print('\n→ Topping up the MF history...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('mfh', ROOT / 'build' / 'mf_pulse_history.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.main(['--max', '2'])
    except Exception as _e:
        print(f'  MF history step skipped: {_e}')

    print('\n→ Labelling episode overrides for the CMS...')
    label_episode_overrides()

    print('\n→ Syncing the menu across pages...')
    sync_nav()

    print('\n→ Checking canonical + analytics tags...')
    sync_head_tags()

    print('\n→ Verifying the measurement is on every page...')
    check_analytics()

    print('\n→ Adding structured data...')
    sync_schema()

    print('\n→ Moving pages off the Tailwind CDN...')
    sync_tailwind()

    print('\n→ Collapsing the fonts URLs into one...')
    sync_fonts()

    print('\n→ Wiring the shared tool layer...')
    sync_tool_assets()

    print('\n→ Checking the newsletter signup...')
    sync_newsletter()

    # One real HTML file per episode, with its title, description and schema
    # in the markup. Everything that shares a link reads the HTML and nothing
    # else, so this is what makes an episode shareable at all.
    print('\n→ Pre-rendering the episode pages...')
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('eppages', ROOT / 'build' / 'episode_pages.py')
        _m = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_m); _m.main()
    except Exception as _e:
        print(f'  Episode page step FAILED: {_e}')
        print('  The committed ep-*.html pages stand; new episodes have no page yet.')

    print('→ Generating sitemap + robots...')
    build_sitemap()
    print()
    print('→ Checking page redirects...')
    check_redirects()
    print()
    print('✓ Build complete')

if __name__ == '__main__':
    main()
