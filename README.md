# TheRepairforge.github.io

The website of [The Repair Forge](https://www.youtube.com/@TheRepairForge): open tools to
diagnose and repair power tool batteries. It presents the published tools and links to their
documentation on GitHub; the tools' own repositories stay the reference.

## Preview

```
pip install -r requirements.txt
python build.py
python tools/check_site.py
python -m http.server -d _site 8000
```

Then open http://localhost:8000/. `python build.py --offline` reuses the string tables cached by
an earlier online build.

## Layout

| Path | What |
|---|---|
| `content/*.html` | one page each: front matter (title, description, path) + the page body |
| `platforms/<slug>.yml` | one battery platform each, rendered by `templates/platform.html` |
| `templates/` | page layout; contains no platform name, platform content is data |
| `site.yml` | navigation, footer, translation review languages, `draft` switch |
| `assets/` | stylesheet, fonts, images, icons |
| `tools/check_site.py` | checks run before every deploy (links, anchors, SEO tags, videos, release tags) |
| `tools/fetch_firmware.py` | copies the web flasher's firmware from the tools' Releases at deploy time |
| `.github/workflows/deploy.yml` | build, check, fetch firmware, deploy to GitHub Pages |

`_site/`, `.cache/` and `firmware/` are build output and never committed.

## Adding a battery platform

A platform appears here only once its firmware has a public Release. Add one
`platforms/<slug>.yml` (copy an existing one), with `line.release` set to the **exact** release
tag that ships it; `check_site.py --online` refuses the deploy if that tag is not a public
Release. The navigation, the footer and the flasher pick it up from that file. Platform URLs and
their section anchors (`#read`, `#wiring`, `#unlock`, `#hardware`, `#videos`) never change once
published: a rename gets a redirect page, never a deletion.

## Licence

Site text and images: CC BY-NC-SA 4.0 (see `LICENSE`). Fonts: Archivo and JetBrains Mono, SIL
Open Font License. Icons: Phosphor, MIT. The tools themselves are licensed in their own
repositories.
