#!/usr/bin/env python3
"""Self-host ESP Web Tools (the web flasher's one script) at deploy time, pinned and verified.

Downloads the pinned npm tarball, checks it against the registry's sha512 integrity pinned here,
and copies its browser build (package/dist/web/) and its Apache-2.0 LICENSE into
_site/vendor/esp-web-tools/. Visitors never load it from a CDN (PLAN 5.3), and no third-party
code sits in this repository's history. To upgrade: change VERSION and INTEGRITY together (the
value is "dist.integrity" at https://registry.npmjs.org/esp-web-tools/<version>).
"""
import base64, hashlib, io, os, sys, tarfile, urllib.request

VERSION = '10.4.0'
INTEGRITY = 'sha512-3pwkeFFm5Fj7UQo8SJNYK5RXrtNCpq6X9QoI6bMT4GBZWgrJqjn0YvM9ihG74BtMoSFYXfmDtkehuxe50PTMPQ=='
URL = f'https://registry.npmjs.org/esp-web-tools/-/esp-web-tools-{VERSION}.tgz'

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(HERE, '_site', 'vendor', 'esp-web-tools')


def main():
    req = urllib.request.Request(URL, headers={'User-Agent': 'fetch_vendor'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    got = 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != INTEGRITY:
        sys.exit(f'esp-web-tools {VERSION}: integrity mismatch, refusing it')
    os.makedirs(DEST, exist_ok=True)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
        for m in t.getmembers():
            if not m.isfile():
                continue
            if m.name.startswith('package/dist/web/'):
                rel = m.name[len('package/dist/web/'):]
            elif m.name == 'package/LICENSE':
                rel = 'LICENSE'
            else:
                continue
            if '..' in rel.split('/'):
                sys.exit(f'esp-web-tools {VERSION}: unexpected path {m.name}')
            dst = os.path.join(DEST, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            io.open(dst, 'wb').write(t.extractfile(m).read())
            n += 1
    if not os.path.exists(os.path.join(DEST, 'install-button.js')):
        sys.exit(f'esp-web-tools {VERSION}: no dist/web/install-button.js in the package')
    print(f'esp-web-tools {VERSION}: {n} files verified and copied')


if __name__ == '__main__':
    main()
