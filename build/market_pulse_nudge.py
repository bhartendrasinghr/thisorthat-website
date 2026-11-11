#!/usr/bin/env python3
"""Turn the Market Pulse review list into something that actually reaches a person.

The nightly Vercel build already works out which figures and sentences no feed
can supply, prints them, and writes them to content/market-pulse-review.json.
That is a perfectly good list nobody will ever read: it lives in a build log and
a file you would have to go and open.

So this runs on GitHub's network instead and renders the same list as an issue
body. The workflow beside it opens one issue, keeps it accurate while it is
open, and closes it when the list empties. One email when something first goes
stale, nothing after that.

It refreshes the figures first, on purpose. One of the nags quotes the live
Nifty back at the prose that contradicts it, and quoting a stale number at a
reader is how you train them to ignore the nag. Refreshing here also tells us
something Vercel cannot: whether the sources answer a second network. If this
job reaches them and the live page is still old, the deploy is the problem.

Writes /tmp/market-pulse-nudge.md and, when GITHUB_OUTPUT is set, the count and
a fingerprint of the list. Touches nothing in the repo that matters: the
refreshed market-pulse.json is a side effect the workflow throws away, because
committing a figure that moves every day would bury the one change worth seeing.
"""

import argparse, hashlib, importlib.util, json, os, re, sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, 'content', 'market-pulse.json')
BODY = '/tmp/market-pulse-nudge.md'
ADDED = '/tmp/market-pulse-added.md'
ADMIN = ('https://thisorthatshow.in/admin/#/collections/'
         'market_pulse/entries/pulse')


def refresher():
    spec = importlib.util.spec_from_file_location(
        'mpr', os.path.join(ROOT, 'build', 'market_pulse_refresh.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plural(n, one, many):
    return one if n == 1 else many


def read_previous(path):
    """What an earlier run of this job already said, parsed back out of its own
    issue body. Cheaper and more honest than keeping state in the repo: the
    issue IS the state, so there is nothing to drift out of sync with it."""
    if not path or not os.path.exists(path):
        return None, []
    text = open(path, encoding='utf-8').read()
    fp = re.search(r'market-pulse-nudge fingerprint (\w+)', text)
    whats = [re.sub(r'\s+·\s+\d+ days since.*$', '', w).strip()
             for w in re.findall(r'^### \d+\. (.+)$', text, re.M)]
    return (fp.group(1) if fp else None), whats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--previous', help='a file holding the last issue body, if any')
    args = ap.parse_args()
    today = date.today()
    mod = refresher()
    doc = json.load(open(DOC, encoding='utf-8'))

    # A refresh failure must not cost us the nag. If the network is down we
    # still know what a person owes the page, because that is computed from the
    # document, not from the feeds.
    res, note = None, None
    try:
        res = mod.main()
    except Exception as e:
        note = (f'The refresh itself failed here with `{type(e).__name__}: {e}`. '
                f'The list below is computed from the figures as last committed, '
                f'so an age may be off by a few days. Worth a look at the '
                f'[workflow log](../../actions/workflows/market-pulse-nudge.yml).')

    if res:
        items, edition, written = res['review'], res['edition'], res['written']
        if res['touched'] == 0:
            note = ('**The refresh updated nothing at all.** Every automatic figure '
                    'on the page is serving whatever was last written, under its old '
                    'date stamp. That is the honest-failure design working, but it '
                    'means no source answered, which is a different problem from '
                    'anything listed below.')
    else:
        items = mod.needs_a_person(doc, today)
        edition, written = doc.get('edition'), doc.get('updated')

    out = [f'**{edition}, written {written}.** '
           f'The scoreboard refreshes itself every night. '
           f'{"This does" if len(items) == 1 else "These do"} not.', '']
    if note:
        out += [f'> {note}', '']

    for i, it in enumerate(items, 1):
        age = (f' · {it["age_days"]} days since it was last touched'
               if it.get('age_days') is not None else '')
        out += [f'### {i}. {it["what"]}{age}', '', it['note'], '']

    out += ['---', '',
            f'Edit in the CMS at [Market Pulse]({ADMIN}), or in '
            f'`content/market-pulse.json` directly.', '',
            'Close this when you are done. If something here is not worth doing '
            'now, close it anyway: nothing reopens for a week.', '']

    fp = hashlib.sha256('\n'.join(sorted(i['what'] for i in items))
                        .encode()).hexdigest()[:12]
    out += [f'<!-- market-pulse-nudge fingerprint {fp} -->']

    open(BODY, 'w', encoding='utf-8').write('\n'.join(out))

    # Only a genuinely new item earns a second email. An item merely getting
    # older does not: he already knows, he was told the first time.
    was_fp, was = read_previous(args.previous)
    added = [i for i in items if i['what'] not in was]
    changed = was_fp != fp
    open(ADDED, 'w', encoding='utf-8').write('\n'.join(
        [f'- **{i["what"]}** · {i["note"]}' for i in added]))

    gh = os.environ.get('GITHUB_OUTPUT')
    if gh:
        with open(gh, 'a') as f:
            f.write(f'count={len(items)}\nfingerprint={fp}\n')
            f.write(f'changed={str(changed).lower()}\n')
            f.write(f'added={len(added)}\n')
            f.write(f'title=Market Pulse: {len(items)} '
                    f'{plural(len(items), "thing", "things")} only you can do\n')

    print(f'{len(items)} item(s), fingerprint {fp}'
          f'{", changed" if changed else ", unchanged"}'
          f', {len(added)} new; body in {BODY}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
