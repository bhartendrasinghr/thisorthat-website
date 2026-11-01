"""Pre-render one real HTML file per episode.

Why this exists. episode-detail.html is a single shell that reads ?v=<id> and
fills the title, description, canonical, og: tags and schema in with JavaScript
after the page loads. Google will usually render that eventually. WhatsApp,
LinkedIn and X never will: none of them run JavaScript, they read the HTML as
it arrives. So every episode anyone shared came out as a blank card with the
title "Episode, ThisOrThat with Bhartendra", which is also the title all 74 of
them handed to Google.

So: take the same values the page's own JS computes, and write them into the
HTML at build time, one file per episode. The JS still runs and still sets the
same values; it just is not the only thing that does any more.

  python3 build/episode_pages.py          write every episode page

Slugs are sticky. content/episode-slugs.json records the first slug an episode
was ever given and that is the one it keeps, so editing a title later does not
silently 404 a URL somebody has already shared or Google has already indexed.
"""
import json, os, re, sys, html
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://thisorthatshow.in'
SHELL = os.path.join(ROOT, 'episode-detail.html')
SLUG_MAP = os.path.join(ROOT, 'content', 'episode-slugs.json')


def kebab(s):
    """A title to the URL-safe part of its slug."""
    s = s.replace('&', ' and ')
    s = re.sub(r"['’‘]", '', s)          # don't turn "kid's" into "kid-s"
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return re.sub(r'-+', '-', s)


def slug_for(ep, taken):
    """ep-073-do-ipos-actually-make-money, capped so URLs stay readable."""
    body = kebab(ep['title'])
    if len(body) > 52:                              # cut on a word, not mid-word
        body = body[:52].rsplit('-', 1)[0]
    body = body.strip('-')
    base = f"ep-{int(ep['n']):03d}-{body}" if body else f"ep-{int(ep['n']):03d}"
    slug, i = base, 2
    while slug in taken:                            # two episodes, one title
        slug = f'{base}-{i}'
        i += 1
    return slug


def load_episodes():
    txt = open(os.path.join(ROOT, 'episodes.js'), encoding='utf-8').read()
    m = re.search(r'window\.EPISODES\s*=\s*(\[.*?\]);', txt, re.S)
    if not m:
        raise SystemExit('episodes.js: could not find window.EPISODES')
    return json.loads(m.group(1))


def load_slugs():
    if os.path.exists(SLUG_MAP):
        return json.load(open(SLUG_MAP, encoding='utf-8'))
    return {}


def content_for(vid):
    p = os.path.join(ROOT, 'content', 'episodes', f'{vid}.json')
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            pass
    return {}


def meta_for(ep, c, url):
    """The same title and description applySeo() builds, computed in Python.

    Kept deliberately in step with episode-detail.html: if that changes, this
    has to change with it, or a share card and the page it opens disagree.
    """
    seo = c.get('seo') or {}
    desc = (seo.get('description') or c.get('summary')
            or f"{ep['title']}. An episode of This or That with Bhartendra, "
               "personal finance, on your side.")
    desc = re.sub(r'\s+', ' ', desc).strip()
    if len(desc) > 300:
        desc = desc[:297].rsplit(' ', 1)[0] + '...'
    title = (f"{seo['title']} | ThisOrThat" if seo.get('title')
             else f"Ep {ep['n']}, {ep['title']} | ThisOrThat")
    img = f"https://i.ytimg.com/vi/{ep['id']}/maxresdefault.jpg"
    return title, desc, img


def schema_for(ep, c, url, title, desc, img):
    video = {
        '@type': 'VideoObject', 'name': ep['title'], 'description': desc,
        'thumbnailUrl': [img, f"https://i.ytimg.com/vi/{ep['id']}/hqdefault.jpg"],
        'embedUrl': f"https://www.youtube.com/embed/{ep['id']}",
        'contentUrl': f"https://www.youtube.com/watch?v={ep['id']}",
        'publisher': {'@type': 'Organization', 'name': 'ThisOrThat with Bhartendra',
                      'logo': {'@type': 'ImageObject', 'url': f'{SITE}/logo.png'}},
    }
    if c.get('uploadDate'):
        video['uploadDate'] = c['uploadDate']
    if c.get('durationISO'):
        video['duration'] = c['durationISO']
    podcast = {
        '@type': 'PodcastEpisode', 'name': ep['title'], 'episodeNumber': ep['n'],
        'url': url, 'description': desc,
        'partOfSeries': {'@type': 'PodcastSeries',
                         'name': 'This or That with Bhartendra', 'url': SITE},
        'associatedMedia': video,
    }
    if c.get('uploadDate'):
        podcast['datePublished'] = c['uploadDate']
    crumbs = {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE},
        {'@type': 'ListItem', 'position': 2, 'name': 'Episodes',
         'item': f'{SITE}/episodes.html'},
        {'@type': 'ListItem', 'position': 3, 'name': ep['title'], 'item': url},
    ]}
    return {'@context': 'https://schema.org', '@graph': [podcast, video, crumbs]}


def a(s):
    """For an HTML attribute value. Titles carry quotes and ampersands."""
    return html.escape(str(s), quote=True)


def render(shell, ep, c, slug):
    url = f'{SITE}/{slug}.html'
    title, desc, img = meta_for(ep, c, url)
    out = shell

    def fill(old, new):
        """Replace exactly once, and refuse to carry on if the shell moved.

        Every one of these failures would otherwise be silent: the tag stays
        empty, the page looks perfect, and only a share card shows the hole.
        """
        nonlocal out
        if old not in out:
            raise SystemExit(f'episode-detail.html has changed, cannot place: {old[:60]}')
        out = out.replace(old, new, 1)

    # The shell ships these empty for the JS to fill. Fill them here instead.
    fill('<title>Episode, ThisOrThat with Bhartendra</title>', f'<title>{a(title)}</title>')
    fill('<meta name="description" id="meta-desc" content="" />',
         f'<meta name="description" id="meta-desc" content="{a(desc)}" />')
    fill('<link rel="canonical" id="canonical" href="" />',
         f'<link rel="canonical" id="canonical" href="{a(url)}" />')
    # The id and the property name differ for the description, so both are
    # spelled out. Getting this wrong is silent: the tag stays empty and only
    # a share card shows it.
    for mid, prop, val in (('og-title', 'title', title), ('og-desc', 'description', desc),
                           ('og-image', 'image', img), ('og-url', 'url', url)):
        fill(f'<meta property="og:{prop}" id="{mid}" content="" />',
             f'<meta property="og:{prop}" id="{mid}" content="{a(val)}" />')
    for mid, name, val in (('tw-title', 'title', title), ('tw-desc', 'description', desc),
                           ('tw-image', 'image', img)):
        fill(f'<meta name="twitter:{name}" id="{mid}" content="" />',
             f'<meta name="twitter:{name}" id="{mid}" content="{a(val)}" />')

    schema = json.dumps(schema_for(ep, c, url, title, desc, img),
                        ensure_ascii=False, separators=(',', ':'))
    # </script> inside JSON would close the tag early.
    schema = schema.replace('</', '<\\/')
    fill('<script type="application/ld+json" id="ld-json"></script>',
         f'<script type="application/ld+json" id="ld-json">{schema}</script>')

    # Which episode this file is, for the page's own JS. It reads ?v= first and
    # falls back to this, so the shell keeps working on its old URL.
    fill('<script src="episodes.js"></script>',
         f'<script>window.EPISODE_ID={json.dumps(ep["id"])};</script>\n'
         '<script src="episodes.js"></script>')
    return out


SLUG_JS_START = '// --- episode slugs, appended by build/episode_pages.py ---'
SLUG_JS_END = '// --- end episode slugs ---'


def write_slug_js(slugs):
    """Publish the slug map to the pages that link to episodes.

    Appended to episodes.js rather than shipped as its own file, because every
    page that needs a link to an episode already loads episodes.js, and a
    second request on every page to carry 74 short strings is not worth it.
    sync.py rewrites episodes.js from scratch, so this re-appends each build.
    """
    path = os.path.join(ROOT, 'episodes.js')
    txt = open(path, encoding='utf-8').read()
    i = txt.find(SLUG_JS_START)
    if i != -1:
        txt = txt[:i].rstrip() + '\n'
    block = (
        f'\n{SLUG_JS_START}\n'
        f'window.EP_SLUGS = {json.dumps(slugs, ensure_ascii=False, sort_keys=True)};\n'
        '// The canonical URL for an episode. Falls back to the old query-string\n'
        '// shell for an episode that has no slug yet, so a link is never dead.\n'
        'window.epHref = function (id) {\n'
        '  var s = window.EP_SLUGS && window.EP_SLUGS[id];\n'
        "  return s ? s + '.html' : 'episode-detail.html?v=' + encodeURIComponent(id);\n"
        '};\n'
        f'{SLUG_JS_END}\n'
    )
    open(path, 'w', encoding='utf-8').write(txt + block)


def main(argv=None):
    shell = open(SHELL, encoding='utf-8').read()
    eps = load_episodes()
    slugs = load_slugs()

    taken = set(slugs.values())
    new = 0
    for ep in eps:
        if ep['id'] not in slugs:
            s = slug_for(ep, taken)
            slugs[ep['id']] = s
            taken.add(s)
            new += 1

    written = 0
    for ep in eps:
        slug = slugs[ep['id']]
        page = render(shell, ep, content_for(ep['id']), slug)
        path = os.path.join(ROOT, f'{slug}.html')
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else None
        if old != page:
            open(path, 'w', encoding='utf-8').write(page)
            written += 1

    json.dump(slugs, open(SLUG_MAP, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, sort_keys=True)
    write_slug_js(slugs)

    # Any ep-*.html left over from an episode that has since been removed.
    live = {f'{s}.html' for s in slugs.values()}
    stale = [f for f in os.listdir(ROOT)
             if re.match(r'^ep-\d{3}-', f) and f.endswith('.html') and f not in live]
    for f in stale:
        os.remove(os.path.join(ROOT, f))

    print(f'  {len(eps)} episode pages ({new} new slug(s), {written} rewritten'
          + (f', {len(stale)} removed' if stale else '') + ')')
    return slugs


if __name__ == '__main__':
    main(sys.argv[1:])
