#!/usr/bin/env python3
"""Checks on the built site (_site/). Exit 1 on any problem: the deploy stops there.

    python tools/check_site.py            # offline checks
    python tools/check_site.py --online   # + GitHub README anchors, YouTube videos, release tags

Offline: identical nav and footer on every page; no em-dash or en-dash in our copy (the strings
quoted for translation review are product data and are skipped); every internal link and anchor
resolves; every page has a title, a description, a canonical matching its path and an og:image;
sitemap.xml lists exactly the indexable pages; every local image exists.
Online: every github.com/<owner>/<repo>[/blob/main/<file>]#anchor points at a heading that exists
on the default branch; every YouTube video is still public (oEmbed); every platform entry's
release tag is a public, non-prerelease Release of its line (D40 point 4).
"""
import argparse, glob, io, json, os, re, sys, urllib.error, urllib.parse, urllib.request
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, '_site')
problems = []


def pages():
    out = {}
    for f in glob.glob(os.path.join(SITE, '**', '*.html'), recursive=True):
        rel = os.path.relpath(f, SITE).replace(os.sep, '/')
        url = '/' + (rel[:-len('index.html')] if rel.endswith('index.html') else rel)
        out[url] = io.open(f, encoding='utf-8').read()
    return out


def visible_text(html):
    html = re.sub(r'<div class="tr-table".*?</div>\s*(?=</details>)', ' ', html, flags=re.S)  # product data
    html = re.sub(r'<(script|style)\b.*?</\1>', ' ', html, flags=re.S)
    return re.sub(r'<[^>]+>', ' ', html)


def check_offline(P, base):
    ids = {u: set(re.findall(r'\bid="([^"]+)"', s)) for u, s in P.items()}
    navs = {re.search(r'<nav class="nav".*?</nav>', s, re.S).group(0).replace(' aria-current="page"', '') for s in P.values()}
    foots = {re.search(r'<footer.*?</footer>', s, re.S).group(0) for s in P.values()}
    if len(navs) != 1: problems.append(f'nav differs between pages ({len(navs)} variants)')
    if len(foots) != 1: problems.append(f'footer differs between pages ({len(foots)} variants)')
    indexable = set()
    for u, s in P.items():
        if re.search(r'[—–]', visible_text(s)):
            problems.append(f'{u}: em-dash or en-dash in visible copy')
        if not re.search(r'<title>[^<]+</title>', s): problems.append(f'{u}: no <title>')
        if 'name="robots" content="noindex"' in s:
            continue
        indexable.add(u)
        if not re.search(r'<meta name="description" content="[^"]+">', s): problems.append(f'{u}: no description')
        can = re.search(r'<link rel="canonical" href="([^"]+)">', s)
        if not can or can.group(1) != base + u: problems.append(f'{u}: canonical missing or not {base + u}')
        if 'property="og:image"' not in s: problems.append(f'{u}: no og:image')
        for h in re.findall(r'(?:href|src)="(/[^"#?]*)(?:#([^"]*))?"', s):
            path, frag = h
            if path.startswith('/assets/') or path.startswith('/translate/files/') or path.endswith(('.xml', '.txt')):
                if not os.path.exists(os.path.join(SITE, path.lstrip('/'))):
                    problems.append(f'{u}: missing file {path}')
                continue
            target = path if path in P else None
            if target is None:
                problems.append(f'{u}: broken link {path}')
            elif frag and frag not in ids[target]:
                problems.append(f'{u}: broken anchor {path}#{frag}')
        for frag in re.findall(r'href="#([^"]+)"', s):
            if frag not in ids[u]: problems.append(f'{u}: broken anchor #{frag}')
    sm = io.open(os.path.join(SITE, 'sitemap.xml'), encoding='utf-8').read()
    listed = {l[len(base):] for l in re.findall(r'<loc>([^<]+)</loc>', sm)}
    if listed != indexable:
        problems.append(f'sitemap mismatch: missing {sorted(indexable - listed)}, extra {sorted(listed - indexable)}')


def gh_slug(heading):
    s = heading.strip().lower()
    s = re.sub(r'[^\w\- ]', '', s)
    return s.replace(' ', '-')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'check_site', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


def check_online(P, owner):
    links = set()
    for s in P.values():
        links |= set(re.findall(rf'href="https://github\.com/{owner}/([\w.-]+)(?:/blob/main/([^"#]+))?#([^"]+)"', s))
    cache = {}
    for repo, path, frag in sorted(links):
        path = path or 'README.md'
        key = (repo, path)
        if key not in cache:
            try:
                md = get(f'https://raw.githubusercontent.com/{owner}/{repo}/main/{path}')
                cache[key] = {gh_slug(h) for h in re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$', md, re.M)}
            except urllib.error.HTTPError as e:
                problems.append(f'{repo}/{path}: HTTP {e.code}'); cache[key] = set()
        if frag not in cache[key]:
            problems.append(f'anchor gone: {repo}/{path}#{frag}')
    vids = set()
    for s in P.values():
        vids |= set(re.findall(r'youtu\.be/([\w-]{11})', s))
    for v in sorted(vids):
        try:
            get('https://www.youtube.com/oembed?format=json&url=' + urllib.parse.quote(f'https://youtu.be/{v}'))
        except urllib.error.HTTPError as e:
            problems.append(f'video {v}: not public (HTTP {e.code})')
    for f in sorted(glob.glob(os.path.join(HERE, 'platforms', '*.yml'))):
        p = yaml.safe_load(io.open(f, encoding='utf-8'))
        repo, tag = p['line']['repo'], p['line']['release']
        try:
            rel = json.loads(get(f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}'))
            if rel.get('draft') or rel.get('prerelease'):
                problems.append(f'{p["slug"]}: {repo} {tag} is a draft or prerelease')
        except urllib.error.HTTPError as e:
            problems.append(f'{p["slug"]}: {repo} {tag} is not a public Release (HTTP {e.code})')
    print(f'online: {len(links)} README anchors, {len(vids)} videos checked')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--online', action='store_true')
    args = ap.parse_args()
    if not os.path.isdir(SITE):
        sys.exit('no _site/: run build.py first')
    site = yaml.safe_load(io.open(os.path.join(HERE, 'site.yml'), encoding='utf-8'))
    P = pages()
    check_offline(P, site['base_url'])
    if args.online:
        check_online(P, site['github_owner'])
    print(f'{len(P)} pages checked')
    if problems:
        print(f'{len(problems)} problem(s):')
        for p in problems:
            print('  - ' + p)
        sys.exit(1)
    print('all clean')


if __name__ == '__main__':
    main()
