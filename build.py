#!/usr/bin/env python3
"""Build the site: content/*.html + platforms/*.yml + templates/ -> _site/ (static HTML).

    pip install -r requirements.txt
    python build.py                 # -> _site/
    python build.py --offline       # reuse the string tables cached in .cache/
    python -m http.server -d _site  # preview on http://localhost:8000/

Pages: one per content/<name>.html (front matter = title, description, path, nav, jsonld), one
per platforms/<slug>.yml through templates/platform.html, the /batteries/ index once there are
two platforms, and the /translate/ pages built from the PUBLISHED string tables of the tool repos.
Nothing in this file or in templates/ names a platform: platform content is data (D40).
"""
import argparse, csv, io, json, os, re, shutil, struct, sys, urllib.parse, urllib.request
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

HERE = os.path.dirname(os.path.abspath(__file__))


def load_front(path):
    text = io.open(path, encoding='utf-8').read()
    m = re.match(r'---\n(.*?)\n---\n(.*)', text, re.S)
    if not m:
        sys.exit(f'{path}: missing front matter')
    return yaml.safe_load(m.group(1)), m.group(2)


def markup_html_fields(p):
    """Platform entries carry HTML fragments: mark them safe, keep plain text escaped."""
    p['hero']['media'] = Markup(p['hero'].get('media', ''))
    p['sections'] = {k: Markup(v) for k, v in (p.get('sections') or {}).items()}
    p['credits'] = [Markup(c) for c in p.get('credits', [])]
    return p


# ------------------------------------------------------------------ translation strings
def fetch(site, repo, path, offline):
    cache = os.path.join(HERE, '.cache', repo, path)
    if not offline:
        url = f'https://raw.githubusercontent.com/{site["github_owner"]}/{repo}/main/{path}'
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read().decode('utf-8')
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        io.open(cache, 'w', encoding='utf-8', newline='\n').write(data)
        return data
    if not os.path.exists(cache):
        sys.exit(f'--offline but {cache} is not cached: run once online')
    return io.open(cache, encoding='utf-8').read()


def strtab(src):
    s = r'"((?:[^"\\]|\\.)*)"'
    rows = re.findall(r'/\*(S_\w+)\*/\s*\{\s*' + r',\s*'.join([s] * 4) + r'\s*\}', src)
    n = len(re.findall(r'/\*S_\w+\*/', src))
    if len(rows) != n:
        sys.exit(f'firmware string table: parsed {len(rows)} of {n} rows, the table changed shape')
    return [dict(zip(('key', 'EN', 'FR', 'DE', 'ES'), r)) for r in rows]


def strtab_ja(src, en):
    """strings_<code>.h (ja, ko, vi): one literal per StrId, enum order; returns {key: text} ('' = not translated)."""
    rows = re.findall(r'/\*(S_\w+)\*/\s*(?:"((?:[^"\\]|\\.)*)"|nullptr)\s*,', src)
    n = len(re.findall(r'/\*S_\w+\*/', src))
    if len(rows) != n or [k for k, _ in rows] != [r['key'] for r in en]:
        sys.exit('strings_<code>.h: rows do not match the main string table, the file changed shape')
    return dict(rows)


def issue_url(site, repo, lang_name, code, key, en, cur):
    q = {'template': 'translation.yml', 'title': f'[{code.upper()}] {key}', 'language': lang_name,
         'key': key, 'english': en, 'current': cur}
    return f'https://github.com/{site["github_owner"]}/{repo}/issues/new?' + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def write_csv(path, rows, code, firmware):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        head = ['key', 'english', f'current_{code}', 'your_suggestion', 'comment']
        if firmware:
            head.insert(3, 'longest_today')
        w.writerow(head)
        for r in rows:
            line = [r['key'], r['en'], r['cur'], '', '']
            if firmware:
                line.insert(3, r['longest'])
            w.writerow(line)


# ------------------------------------------------------------------ build
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, '_site'))
    ap.add_argument('--platforms', default=os.path.join(HERE, 'platforms'),
                    help='platform entries; a PRIVATE pending folder may be previewed, never into this repo')
    ap.add_argument('--offline', action='store_true')
    args = ap.parse_args()
    out, pdir = os.path.abspath(args.out), os.path.abspath(args.platforms)
    inside = lambda p: os.path.commonpath([p, HERE]) == HERE
    if inside(out) and not inside(pdir):
        sys.exit('refused: previewing entries from outside this repo must write outside it (D40 point 5)')

    site = yaml.safe_load(io.open(os.path.join(HERE, 'site.yml'), encoding='utf-8'))
    platforms = [markup_html_fields(yaml.safe_load(io.open(os.path.join(pdir, f), encoding='utf-8')))
                 for f in sorted(os.listdir(pdir)) if f.endswith('.yml')]
    for p in platforms:
        if p['line']['release'] in ('', 'latest', None):
            sys.exit(f'{p["slug"]}: line.release must be an exact tag, never "latest" (D40 point 4)')

    nav = []
    for item in site['nav']:
        item = dict(item)
        if item['key'] == 'batteries':
            item['href'] = f'/{platforms[0]["slug"]}/' if len(platforms) == 1 else '/batteries/'
        nav.append(item)

    env = Environment(loader=FileSystemLoader(os.path.join(HERE, 'templates')),
                      autoescape=select_autoescape(['html']), trim_blocks=False, lstrip_blocks=False)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    built = []

    def emit(template, page, **ctx):
        html = env.get_template(template).render(site=site, nav=nav, platforms=platforms, page=page, **ctx)
        rel = page['path'] if page['path'].endswith('.html') else page['path'] + 'index.html'
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        io.open(dst, 'w', encoding='utf-8', newline='\n').write(html)
        built.append(page)

    for f in sorted(os.listdir(os.path.join(HERE, 'content'))):
        if f.endswith('.html'):
            front, body = load_front(os.path.join(HERE, 'content', f))
            if front.get('jsonld'):
                front['jsonld'] = Markup(front['jsonld'].replace('</', '<\\/'))
            emit('page.html', front, body=Markup(body))

    for p in platforms:
        emit('platform.html', {'title': p['title'], 'title_suffix': True, 'description': p['description'],
                               'path': p['slug'] + '/', 'nav': 'batteries', 'og_image': p.get('og_image')}, p=p)
    if len(platforms) > 1:
        emit('batteries.html', {'title': 'Batteries', 'title_suffix': True, 'path': 'batteries/', 'nav': 'batteries',
                                'description': 'Pick the platform of your battery: what is read, what can be repaired.'})

    # translation review pages (PLAN 2.8)
    tr = site['translate']
    fw_raw = strtab(fetch(site, 'PocketOBI', tr['sources']['PocketOBI']['file'], args.offline))
    ps_dir = tr['sources']['PackScope']['dir']
    ps_en = json.loads(fetch(site, 'PackScope', f'{ps_dir}/en.json', args.offline))
    langs = []
    for code, meta in tr['languages'].items():
        sep = 'firmware' in meta                 # its own table file (strings_<code>.h), one literal per StrId
        cjk = sep and not meta.get('ascii')      # drawn with the CJK font: no ASCII rule, no width column
        cur = strtab_ja(fetch(site, 'PocketOBI', meta['firmware'], args.offline), fw_raw) if sep else {r['key']: r[code.upper()] for r in fw_raw}
        fw = [{'key': r['key'], 'en': r['EN'], 'cur': cur[r['key']],
               'longest': '' if cjk else max(len(r[c]) for c in ('EN', 'FR', 'DE', 'ES')),
               'issue': issue_url(site, 'PocketOBI', meta['name'], code, r['key'], r['EN'], cur[r['key']])} for r in fw_raw]
        write_csv(os.path.join(out, 'translate', 'files', f'pocketobi-{code}.csv'), fw, code, not cjk)
        ps = []
        if meta.get('packscope', True):
            ps_tr = json.loads(fetch(site, 'PackScope', f'{ps_dir}/{code}.json', args.offline))
            ps = [{'key': k, 'en': v, 'cur': ps_tr.get(k, ''),
                   'issue': issue_url(site, 'PackScope', meta['name'], code, k, v, ps_tr.get(k, ''))} for k, v in ps_en.items()]
            write_csv(os.path.join(out, 'translate', 'files', f'packscope-{code}.csv'), ps, code, False)
        with open(os.path.join(HERE, 'assets', 'img', 'translate', f'po-{code}-sheet.png'), 'rb') as f:
            sheet = struct.unpack('>II', f.read(24)[16:24])   # PNG IHDR: width, height
        l = {'code': code, 'name': meta['name'], 'native': meta['native'], 'n_fw': len(fw), 'n_ps': len(ps),
             'cjk': cjk, 'by_native': meta.get('by_native', False), 'sheet_w': sheet[0], 'sheet_h': sheet[1]}
        langs.append(l)
        tools = 'PocketOBI and PackScope' if ps else 'PocketOBI'
        emit('translate_lang.html', {'title': f'Review the {meta["name"]} translation of {tools}', 'title_suffix': True,
                                     'description': f'Native {meta["name"]} speakers: check the {tools} strings and suggest fixes on GitHub.',
                                     'path': f'translate/{code}/', 'nav': 'translate'}, l=l, fw=fw, ps=ps)
    names = [l['name'] for l in langs]
    def join(w, last):
        return w[0] if len(w) == 1 else ', '.join(w[:-1]) + f' {last} ' + w[-1]
    drafts = [l['name'] for l in langs if not l['by_native']]
    natives = [l['name'] for l in langs if l['by_native']]
    emit('translate_hub.html', {'title': 'Help translate PocketOBI and PackScope', 'title_suffix': True,
                                'description': f'Native {join(names, "and")} speakers: review the PocketOBI and PackScope translations and suggest fixes on GitHub.',
                                'path': 'translate/', 'nav': 'translate'}, langs=langs,
         lang_names=join(names, 'or'), lang_drafts=join(drafts, 'and'), lang_natives=join(natives, 'and') if natives else '')

    shutil.copytree(os.path.join(HERE, 'assets'), os.path.join(out, 'assets'))
    io.open(os.path.join(out, 'robots.txt'), 'w', newline='\n').write(f'User-agent: *\nAllow: /\n\nSitemap: {site["base_url"]}/sitemap.xml\n')
    urls = ''.join(f'  <url><loc>{site["base_url"]}/{p["path"]}</loc></url>\n' for p in built if not p.get('noindex'))
    io.open(os.path.join(out, 'sitemap.xml'), 'w', newline='\n').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + '</urlset>\n')
    print(f'{len(built)} pages, {len(platforms)} platform(s), {len(langs)} review language(s) -> {out}')


if __name__ == '__main__':
    main()
