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

# ─── Frontmatter + markdown parsing (no external deps) ───────────────────
def parse_frontmatter(text):
    """Extract YAML-like frontmatter between leading --- markers. Returns (meta_dict, body)."""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
    if not m:
        return {}, text
    meta_block, body = m.group(1), m.group(2)
    meta = {}
    for line in meta_block.splitlines():
        line = line.rstrip()
        if not line or line.startswith('#'): continue
        if ':' not in line: continue
        k, _, v = line.partition(':')
        k = k.strip()
        v = v.strip()
        # Strip quotes
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1].replace('\\"', '"').replace("\\'", "'")
        # Type coerce
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

# ─── Main ────────────────────────────────────────────────────────────────
def main():
    print('=== ThisOrThat build ===')
    print()
    print('→ Compiling articles...')
    build_articles()
    print()
    # YouTube sync can fail on Netlify if network is blocked — make optional
    if os.environ.get('SKIP_YT_SYNC') != '1':
        sync_youtube()
    print()
    print('✓ Build complete')

if __name__ == '__main__':
    main()
