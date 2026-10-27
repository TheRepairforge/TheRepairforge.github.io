#!/usr/bin/env python3
"""Fetch the firmware files the web flasher serves, from the tools' public Releases.

Browsers cannot download Release assets (no CORS headers), so the deploy copies them into the
site. For each firmware line named by a platform entry (platforms/*.yml: line.repo +
line.release), download that exact Release's `*-parts.zip` files and its SHA256SUMS, verify every
checksum, and unpack each build into _site/firmware/<repo>/<env>/ with an ESP Web Tools
manifest.json next to the parts. The flasher uses the separate parts, never the merged image
(PLAN 5.3): an update then leaves NVS alone, so the language and the touch calibration survive.
Chip and offsets come from the OFFSETS.txt that the tool's release script puts in each zip.

Fails when a Release carries no parts, or when a platform's board has no build in it: the
previous deployment stays live, never a flasher pointing at nothing.
"""
import glob, hashlib, io, json, os, re, sys, urllib.request, zipfile
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, '_site')
CHIP_FAMILY = {'esp32c3': 'ESP32-C3', 'esp32': 'ESP32', 'esp32s3': 'ESP32-S3'}   # esptool chip -> ESP Web Tools chipFamily


def get(url, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'fetch_firmware', 'Accept': 'application/octet-stream' if binary else 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def manifest(z, repo, tag, env):
    """OFFSETS.txt = "Flash offsets (chip <chip>):" then one "<hex offset> <file>" per line."""
    lines = z.read('OFFSETS.txt').decode().splitlines()
    chip = re.search(r'\(chip (\w+)\)', lines[0])
    if not chip or chip.group(1) not in CHIP_FAMILY:
        sys.exit(f'{repo} {tag} {env}: OFFSETS.txt names no known chip')
    parts = []
    for line in lines[1:]:
        if line.strip():
            off, name = line.split()
            if name not in z.namelist():
                sys.exit(f'{repo} {tag} {env}: OFFSETS.txt lists {name}, absent from the zip')
            parts.append({'path': name, 'offset': int(off, 16)})
    return {'name': f'{repo} ({env})', 'version': tag, 'new_install_prompt_erase': True,
            'builds': [{'chipFamily': CHIP_FAMILY[chip.group(1)], 'parts': parts}]}


def main():
    owner = yaml.safe_load(io.open(os.path.join(HERE, 'site.yml'), encoding='utf-8'))['github_owner']
    lines = {}
    for f in glob.glob(os.path.join(HERE, 'platforms', '*.yml')):
        p = yaml.safe_load(io.open(f, encoding='utf-8'))
        lines.setdefault((p['line']['repo'], p['line']['release']), []).append(p)
    repos = [repo for repo, _ in lines]
    if len(repos) != len(set(repos)):
        sys.exit('two platforms name different releases of one firmware line: the flasher serves one per line')
    for (repo, tag), plats in sorted(lines.items()):
        rel = json.loads(get(f'https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}'))
        assets = {a['name']: a['browser_download_url'] for a in rel.get('assets', [])}
        sums_name = next((n for n in ('SHA256SUMS', 'SHA256SUMS.txt') if n in assets), None)
        prefix = f'{repo}-{tag}-'
        zips = sorted(n for n in assets if n.startswith(prefix) and n.endswith('-parts.zip'))
        if not zips or not sums_name:
            sys.exit(f'{repo} {tag}: the Release has no firmware parts + SHA256SUMS yet')
        sums = {}
        for line in get(assets[sums_name], True).decode().splitlines():
            if line.strip():
                h, name = line.split(None, 1)
                sums[name.lstrip('*').strip()] = h.lower()
        envs = []
        for n in zips:
            data = get(assets[n], True)
            if hashlib.sha256(data).hexdigest() != sums.get(n):
                sys.exit(f'{repo} {tag}: checksum mismatch on {n}')
            env = n[len(prefix):-len('-parts.zip')]
            z = zipfile.ZipFile(io.BytesIO(data))
            man = manifest(z, repo, tag, env)
            dest = os.path.join(SITE, 'firmware', repo, env)
            os.makedirs(dest, exist_ok=True)
            for part in man['builds'][0]['parts']:
                io.open(os.path.join(dest, part['path']), 'wb').write(z.read(part['path']))
            io.open(os.path.join(dest, 'manifest.json'), 'w', encoding='utf-8', newline='\n').write(json.dumps(man, indent=2) + '\n')
            envs.append(env)
        for p in plats:
            missing = [b for b in p.get('boards', []) if b not in envs]
            if missing:
                sys.exit(f'{p["slug"]}: {repo} {tag} has no build for board(s) {", ".join(missing)}')
        print(f'{repo} {tag}: {len(envs)} builds verified, manifests written ({", ".join(envs)})')


if __name__ == '__main__':
    main()
