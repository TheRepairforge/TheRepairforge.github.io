#!/usr/bin/env python3
"""Fetch the firmware files the web flasher serves, from the tools' public Releases.

Browsers cannot download Release assets (no CORS headers), so the deploy copies them into the
site. For each firmware line named by a platform entry (platforms/*.yml: line.repo +
line.release), download that exact Release's .bin files and SHA256SUMS into
_site/firmware/<repo>/<tag>/ and verify every checksum. Fails when a Release carries no
binaries: the previous deployment stays live, never a flasher pointing at nothing.

The ESP Web Tools manifests (one per firmware line x board, D40 point 1) are written here once
the release asset names are fixed by the tool's release process.
"""
import glob, hashlib, io, json, os, sys, urllib.request
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, '_site')


def get(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'fetch_firmware', 'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    owner = yaml.safe_load(io.open(os.path.join(HERE, 'site.yml'), encoding='utf-8'))['github_owner']
    lines = {}
    for f in glob.glob(os.path.join(HERE, 'platforms', '*.yml')):
        p = yaml.safe_load(io.open(f, encoding='utf-8'))
        lines[(p['line']['repo'], p['line']['release'])] = p['slug']
    for (repo, tag), slug in sorted(lines.items()):
        rel = json.loads(get(f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}'))
        assets = {a['name']: a['browser_download_url'] for a in rel.get('assets', [])}
        bins = [n for n in assets if n.endswith('.bin')]
        if not bins or 'SHA256SUMS' not in assets:
            sys.exit(f'{repo} {tag} ({slug}): the Release has no firmware binaries + SHA256SUMS yet')
        dest = os.path.join(SITE, 'firmware', repo, tag)
        os.makedirs(dest, exist_ok=True)
        sums = {}
        for line in get(assets['SHA256SUMS'], True).decode().splitlines():
            if line.strip():
                h, name = line.split(None, 1)
                sums[name.lstrip('*').strip()] = h.lower()
        for n in bins:
            data = get(assets[n], True)
            if hashlib.sha256(data).hexdigest() != sums.get(n):
                sys.exit(f'{repo} {tag}: checksum mismatch on {n}')
            io.open(os.path.join(dest, n), 'wb').write(data)
        print(f'{repo} {tag}: {len(bins)} binaries verified')


if __name__ == '__main__':
    main()
