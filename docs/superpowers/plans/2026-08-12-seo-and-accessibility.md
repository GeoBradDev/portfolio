# SEO and Accessibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every page real head metadata, give the homepage a share card and structured data, add the three missing site-root files, and close the accessibility defects that keep icon links, form fields, and keyboard focus from being usable.

**Architecture:** Source-level changes to four static pages plus one stylesheet, backed by a new standard-library verifier, `tools/verify_seo_a11y.py`, built the same way as its three siblings: it discovers pages with a glob over `*.html`, reads the site host from `CNAME` rather than hardcoding it, prints one PASS/FAIL line per assertion, and exits non-zero on any failure. Each task writes its checks first, watches them fail, then edits the markup until they pass. One existing verifier changes too: `verify_security.py` currently runs `node --check` over every inline `<script>` without a `src`, which rejects a JSON-LD block outright, so it learns to route `application/ld+json` to a JSON parser instead.

**Tech Stack:** Vanilla HTML5, CSS3, Bootstrap 3.3.7, jQuery 3.7.1, Python 3 standard library for the verifiers, Pillow for the one-time share-card generation.

## Global Constraints

- No emojis and no em dashes in any file, commit message, comment, or PR text.
- Never write TypeScript. The site is vanilla JavaScript.
- Verifiers are standard library only. Pillow is allowed in `tools/make_og_card.py` because that script is run by hand to regenerate a committed asset, exactly like `tools/optimize_images.py`, and is never part of the gate.
- No build system, no npm, no bundler. Files are edited directly and served as-is.
- Font Awesome is 4.7.0. Use bare `fa fa-*` classes. The `fas`/`fab`/`far` style classes render nothing here and `verify_security.py` rejects them.
- The site host is `www.geobrad.dev`, and it is read from `CNAME` in every verifier rather than hardcoded, so changing the custom domain does not leave a script asserting the old one.
- Do not change any `name` attribute on the contact form. `name`, `email`, `message`, `_honey`, `_next`, and `_subject` are the FormSubmit wire contract; renaming one silently changes or breaks the mail that gets sent.
- `resume.html` and `privacy.html` stay unlinked from the nav and footer. Issue 18's owner decision stands. This plan adds `noindex` to both, which is the search-engine half of the same decision.
- All four verifiers must exit 0 at the end of every task: `verify_assets.py`, `verify_security.py`, `verify_content.py`, `verify_interactivity.py`, plus the new `verify_seo_a11y.py`.

## File Structure

**Created:**
- `tools/verify_seo_a11y.py` - the gate for everything in this plan. Grows one check function per task.
- `tools/make_og_card.py` - one-time generator for `img/og-card.jpg`. Run by hand, requires Pillow, never part of the gate.
- `img/og-card.jpg` - the 1200x630 share card, committed.
- `robots.txt`, `sitemap.xml`, `404.html` - site-root files GitHub Pages serves directly.

**Modified:**
- `index.html` - canonical, OG/Twitter tags, JSON-LD, skip link, accessible names, `rel` on external links, form labels, contrast values in the embedded portfolio CSS.
- `resume.html` - description, canonical, `noindex`, accessible names on decorative icons.
- `thanks.html` - description, canonical.
- `privacy.html` - wrapped in a document shell, since the file is currently a bare Termly fragment with no doctype, `<html>`, `<head>`, or `<title>`.
- `css/style.css` - focus-visible rules replacing the blanket `outline: none`, and the skip-link rule.
- `tools/verify_security.py` - route `application/ld+json` blocks to a JSON parser instead of `node --check`.
- `tools/verify_assets.py` - add `img/og-card.jpg` to `SHIPPED_VARIANTS`.

---

### Task 1: Verifier scaffold and per-page head metadata

Every page gets a description and a canonical URL. `resume.html` and `privacy.html` additionally get `noindex`, because the owner keeps both reachable by URL and out of search. `privacy.html` has no head to put any of this in, so it gets a document shell first.

**Files:**
- Create: `tools/verify_seo_a11y.py`
- Modify: `index.html:10-12`, `resume.html:3-7`, `thanks.html:3-11`, `privacy.html:1` and end of file

**Interfaces:**
- Produces: `read(path)`, `read_or_fail(path)`, `check(condition, message)`, `fail(message)`, `site_host()`, `HTML_PAGES`, `ROOT`, and the `failures` list. Every later task adds a `check_*` function to this file and registers it in `main()`.

- [ ] **Step 1: Write the failing test**

Create `tools/verify_seo_a11y.py`:

```python
#!/usr/bin/env python3
"""Check the SEO and accessibility criteria from issue 19.

Run from the repository root:

    python3 tools/verify_seo_a11y.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.

Source-level only. That a crawler actually renders the share card, and that a
screen reader actually announces the names asserted here, has to be driven in
a browser. Lighthouse and axe are the runtime half of this gate.

Two pages are deliberately kept out of search, which is the search-engine half
of the owner decision issue 18 recorded:

  - resume.html is sent on request rather than published.
  - privacy.html belongs to a different project and is hosted here only so its
    existing URL keeps resolving.

Neither is exempt from any check here. Both are swept by the same *.html glob
every other verifier uses.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RESUME = ROOT / "resume.html"
PRIVACY = ROOT / "privacy.html"
THANKS = ROOT / "thanks.html"
STYLE_CSS = ROOT / "css" / "style.css"
CNAME = ROOT / "CNAME"

# Every page at the repo root, discovered from the filesystem rather than
# hardcoded, so a page added later is covered instead of silently exempt.
# Same rule verify_assets.py, verify_security.py, and verify_content.py use.
HTML_PAGES = sorted(ROOT.glob("*.html"))

# Which pages search engines may list. Anything not named here must carry a
# robots noindex. A page added later lands in neither set and fails the
# "every page states an indexing policy" check, which is the point: the
# decision gets made deliberately rather than by default.
INDEXABLE = {"index.html"}
NOINDEX = {"resume.html", "privacy.html", "thanks.html"}

failures = []


def fail(message):
    failures.append(message)
    print("  FAIL  " + message)


def check(condition, message):
    if condition:
        print("  PASS  " + message)
    else:
        fail(message)
    return condition


def read(path):
    """Return path's text, or None if the file does not exist.

    Same contract as verify_security.read: a missing file becomes one FAIL
    line from the caller instead of a traceback that kills every remaining
    check partway through the run.
    """
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def read_or_fail(path):
    """read(), plus turning a missing file into one FAIL line instead of None."""
    text = read(path)
    check(text is not None, "%s exists" % path.relative_to(ROOT))
    return text


def site_host():
    """The host GitHub Pages serves this site on, per the CNAME file.

    Read rather than hardcoded so that changing the custom domain does not
    leave this script asserting the old one. Same helper verify_content.py
    uses to validate the contact form's _next.
    """
    text = read(CNAME)
    return text.strip() if text else None


def meta_content(source, **attrs):
    """The content attribute of the first <meta> matching every attr given.

    meta_content(src, name="description") finds <meta name="description"
    content="...">, in either attribute order, and returns the content
    string. Returns None when no such tag exists.
    """
    for tag in re.findall(r"<meta\b[^>]*>", source, re.I):
        if all(
            re.search(r'\b%s\s*=\s*"%s"' % (key, re.escape(value)), tag, re.I)
            for key, value in attrs.items()
        ):
            content = re.search(r'\bcontent\s*=\s*"([^"]*)"', tag, re.I)
            return content.group(1) if content else ""
    return None


def canonical_href(source):
    """The href of <link rel="canonical">, or None."""
    for tag in re.findall(r"<link\b[^>]*>", source, re.I):
        if re.search(r'\brel\s*=\s*"canonical"', tag, re.I):
            href = re.search(r'\bhref\s*=\s*"([^"]*)"', tag, re.I)
            return href.group(1) if href else ""
    return None


def check_every_page_is_a_complete_document():
    """A page with no head cannot carry a canonical or a description.

    privacy.html shipped for years as a bare Termly fragment: no doctype, no
    <html>, no <head>, no <title>, no charset, no viewport. Browsers render
    that in quirks mode and guess at the encoding. Every check below assumes
    a head exists to put tags in, so assert the shell first.
    """
    print("\nEvery page is a complete HTML document")

    titles = {}
    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        name = path.name

        check(
            source.lstrip().lower().startswith("<!doctype html>"),
            "%s opens with a doctype" % name,
        )
        check(
            re.search(r"<html\b[^>]*\blang\s*=", source, re.I) is not None,
            "%s declares a language" % name,
        )
        check(
            re.search(r"<meta\b[^>]*charset", source, re.I) is not None,
            "%s declares a charset" % name,
        )
        check(
            meta_content(source, name="viewport") is not None,
            "%s declares a viewport" % name,
        )
        title = re.search(r"<title>(.*?)</title>", source, re.S | re.I)
        if check(
            title is not None and title.group(1).strip() != "",
            "%s has a non-empty title" % name,
        ):
            # Two pages sharing a title is the same defect as two sharing a
            # description: it tells a crawler, and a browser's tab strip and
            # history, that they are one page. index.html and resume.html
            # both read "Brad Stricherz | Geospatial Software Engineer"
            # before this check existed.
            text = title.group(1).strip()
            duplicate = titles.get(text)
            check(
                duplicate is None,
                "%s's title is unique%s"
                % (name, "" if duplicate is None else ", but matches %s" % duplicate),
            )
            titles[text] = name


def check_every_page_has_a_description():
    """Without one, the search snippet is whatever text the crawler grabs.

    Required on the noindex pages too. A meta description is also what a
    link unfurl falls back to, and noindex stops a page being listed, not
    being shared.
    """
    print("\nEvery page has its own meta description")

    seen = {}
    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        name = path.name

        description = meta_content(source, name="description")
        if not check(description is not None, "%s has a meta description" % name):
            continue
        check(
            len(description.strip()) >= 50,
            "%s's description is a real sentence, not a stub (%d chars)"
            % (name, len(description.strip())),
        )
        # Two pages sharing a description tells a crawler they are the same
        # page, which is the problem canonical tags exist to solve.
        duplicate = seen.get(description.strip())
        check(
            duplicate is None,
            "%s's description is unique%s"
            % (name, "" if duplicate is None else ", but matches %s" % duplicate),
        )
        seen[description.strip()] = name


def check_every_page_declares_a_canonical():
    """The site answers on both geobrad.dev and www.geobrad.dev.

    Without a canonical those are two URLs for one page and ranking signals
    split between them. The host comes from CNAME so that changing the custom
    domain fails this check until the pages agree.
    """
    print("\nEvery page declares a canonical URL on this host")

    host = site_host()
    if not check(host is not None, "CNAME names the site host"):
        return

    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        name = path.name

        href = canonical_href(source)
        if not check(href is not None, "%s declares a canonical URL" % name):
            continue
        check(
            href.startswith("https://%s/" % host),
            "%s's canonical is https and on %s (%s)" % (name, host, href),
        )
        # index.html canonicalizes to the bare root, every other page to its
        # own filename. A canonical pointing at the wrong page deindexes the
        # page that declares it.
        expected = "https://%s/" % host
        if name != "index.html":
            expected = "https://%s/%s" % (host, name)
        check(href == expected, "%s's canonical points at itself (%s)" % (name, expected))


def check_indexing_policy_is_explicit():
    """Unlinked is not unindexed. Say so in the markup.

    resume.html and privacy.html are reachable by URL and linked from
    nowhere, which stops a visitor finding them and does nothing to stop a
    crawler. A page not named in either set below fails, so adding a page
    forces the decision instead of defaulting to indexed.
    """
    print("\nEvery page states an indexing policy")

    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        name = path.name

        robots = meta_content(source, name="robots")
        if name in INDEXABLE:
            check(
                robots is None or "noindex" not in robots.lower(),
                "%s is indexable and carries no noindex" % name,
            )
        elif name in NOINDEX:
            check(
                robots is not None and "noindex" in robots.lower(),
                "%s carries a robots noindex" % name,
            )
        else:
            fail(
                "%s is in neither INDEXABLE nor NOINDEX; decide whether search "
                "engines may list it and add it to one" % name
            )


def main():
    check_every_page_is_a_complete_document()
    check_every_page_has_a_description()
    check_every_page_declares_a_canonical()
    check_indexing_policy_is_explicit()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL. `privacy.html` fails every document-shell check, all four pages fail the canonical check, three fail the description check, and three fail the noindex check.

- [ ] **Step 3: Add the head metadata to index.html**

In `index.html`, immediately after the existing `<meta name="description" ...>` on line 11, add:

```html
    <link rel="canonical" href="https://www.geobrad.dev/">
```

- [ ] **Step 4: Add the head metadata to resume.html**

In `resume.html`, replace lines 4 to 7 with:

```html
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Resume | Brad Stricherz, Geospatial Software Engineer</title>
    <meta name="description" content="Resume of Brad Stricherz: 15 years of geospatial work, WebGIS platforms on React and OpenLayers, spatial backends on Django Ninja and PostGIS.">
    <link rel="canonical" href="https://www.geobrad.dev/resume.html">

    <!-- The resume is sent on request rather than published, which is why no
         page links to it. Unlinked keeps a visitor from finding it and does
         nothing to stop a crawler, so say it here too. robots.txt must not
         also Disallow this page: a crawler that is refused the file never
         reads the tag telling it not to list the file. -->
    <meta name="robots" content="noindex, follow">

    <link rel="stylesheet" href="css/font-awesome.min.css">
```

- [ ] **Step 5: Add the head metadata to thanks.html**

In `thanks.html`, after the existing `<meta name="robots" content="noindex">` on line 11, add:

```html
    <meta name="description" content="Confirmation that your message to Brad Stricherz at GeoBrad.dev was sent, with a link back to the site.">
    <link rel="canonical" href="https://www.geobrad.dev/thanks.html">
```

- [ ] **Step 6: Wrap privacy.html in a document shell**

`privacy.html` currently begins at `<style>` on line 1 and ends at `</div>`. Do not touch anything between. Prepend:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>Privacy Policy | GeoBrad.dev</title>
    <meta name="description" content="Privacy policy describing what personal information is collected, how it is used and shared, and the choices and rights available to visitors.">
    <link rel="canonical" href="https://www.geobrad.dev/privacy.html">

    <!-- This policy belongs to a different project and is hosted here only so
         its existing URL keeps resolving, so it stays out of search results
         under this domain. robots.txt must not also Disallow it, or a crawler
         never reads this tag. -->
    <meta name="robots" content="noindex, follow">

    <link rel="icon" href="img/favicon.ico">
</head>
<body>
<!-- Everything below is a Termly-generated paste, kept verbatim. A regenerated
     policy replaces the content inside this body; it does not replace the file,
     because the file is what carries the head above. -->
```

and append after the final `</div>`:

```html
</body>
</html>
```

- [ ] **Step 7: Run the new verifier to confirm it passes**

Run: `python3 tools/verify_seo_a11y.py`
Expected: PASS, "All checks passed."

- [ ] **Step 8: Run the existing gate to confirm nothing regressed**

Run each and expect exit 0:

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_content.py
python3 tools/verify_interactivity.py
```

Note: `verify_content.py` and `verify_security.py` both sweep `privacy.html`. The shell adds a `<link rel="icon">`, which is the file's first `<link>` tag, and no `http://` URL, so both stay green.

- [ ] **Step 9: Commit**

```bash
git add tools/verify_seo_a11y.py index.html resume.html thanks.html privacy.html
git commit -m "feat: give every page a description, a canonical URL, and an indexing policy"
```

---

### Task 2: The share card image and Open Graph tags

**Files:**
- Create: `tools/make_og_card.py`, `img/og-card.jpg`
- Modify: `index.html` head, `tools/verify_seo_a11y.py`, `tools/verify_assets.py:53-65`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `site_host`, `meta_content`, `INDEX` from Task 1.
- Produces: `img/og-card.jpg` at exactly 1200x630, under 200 KB.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
# The share card, and the budget it has to fit. Twitter's limit is 5 MB and
# Facebook's is 8 MB, so 200 KB is not a platform limit; it is the issue's
# own budget, set because a card nobody waits for is a card nobody sees.
OG_CARD = ROOT / "img" / "og-card.jpg"
OG_CARD_BUDGET = 200 * 1024
OG_CARD_SIZE = (1200, 630)


def jpeg_dimensions(path):
    """(width, height) of a JPEG, read from its SOF marker.

    Pillow would answer this in one line, but every verifier in this repo is
    standard library only so that the gate runs anywhere Python 3 does. A
    JPEG is a chain of length-prefixed segments; the frame header (any SOFn
    except the four that are not frame headers) carries height then width as
    big-endian 16-bit values right after a one-byte sample precision.
    """
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        return None
    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            return None
        marker = data[offset + 1]
        # Standalone markers carry no length payload.
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        # SOF0 through SOF15, excluding DHT (C4), JPG (C8), and DAC (CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[offset + 5:offset + 7], "big")
            width = int.from_bytes(data[offset + 7:offset + 9], "big")
            return (width, height)
        offset += 2 + length
    return None


def check_share_card_exists_and_fits():
    """A card that 404s or crawls slowly is the same as no card.

    Dimensions are asserted, not assumed. 1200x630 is the size every unfurler
    treats as a large summary card; off by enough and Twitter and LinkedIn
    fall back to a small thumbnail or drop the image entirely.
    """
    print("\nThe share card exists, is the right size, and fits its budget")

    if not check(OG_CARD.exists(), "img/og-card.jpg exists"):
        return

    size = OG_CARD.stat().st_size
    check(
        size < OG_CARD_BUDGET,
        "img/og-card.jpg is %.1f KB, under the %d KB budget"
        % (size / 1024.0, OG_CARD_BUDGET // 1024),
    )

    dimensions = jpeg_dimensions(OG_CARD)
    check(
        dimensions == OG_CARD_SIZE,
        "img/og-card.jpg is %dx%d (found %s)"
        % (OG_CARD_SIZE[0], OG_CARD_SIZE[1], dimensions),
    )


def check_homepage_carries_share_tags():
    """A bare URL in Slack or LinkedIn is a wasted introduction.

    Only index.html carries these. The other three pages are noindex and
    unlinked, and a card on a page nobody is meant to share is markup that
    can only ever go stale.

    og:image has to be absolute. A relative one resolves against the
    crawler's own base, not the page's, and the image silently never loads.
    """
    print("\nThe homepage carries Open Graph and Twitter card tags")

    source = read_or_fail(INDEX)
    if source is None:
        return

    host = site_host()
    if not check(host is not None, "CNAME names the site host"):
        return

    required = {
        "og:type": "website",
        "og:site_name": None,
        "og:title": None,
        "og:description": None,
        "og:url": "https://%s/" % host,
        "og:image": "https://%s/img/og-card.jpg" % host,
        "og:image:width": "1200",
        "og:image:height": "630",
        "og:image:alt": None,
    }
    for prop, expected in required.items():
        content = meta_content(source, property=prop)
        if not check(content is not None, "index.html declares %s" % prop):
            continue
        if expected is None:
            check(content.strip() != "", "%s is not empty" % prop)
        else:
            check(content == expected, "%s is %s (found %s)" % (prop, expected, content))

    card = meta_content(source, name="twitter:card")
    check(card == "summary_large_image", "index.html sets twitter:card to summary_large_image")

    # The three pages that are not meant to be shared must not carry a card
    # that would rot. This is the check that keeps a future copy-paste of the
    # homepage head from spreading stale og:url values across the site.
    for path in HTML_PAGES:
        if path == INDEX:
            continue
        other = read(path)
        if other is None:
            continue
        check(
            meta_content(other, property="og:url") is None,
            "%s carries no og:url to go stale" % path.name,
        )
```

Register both in `main()`, after `check_indexing_policy_is_explicit()`:

```python
    check_share_card_exists_and_fits()
    check_homepage_carries_share_tags()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL, starting with "img/og-card.jpg exists" and every `og:` tag.

- [ ] **Step 3: Write the generator**

Create `tools/make_og_card.py`:

```python
#!/usr/bin/env python3
"""Generate img/og-card.jpg, the 1200x630 card link unfurlers show.

Run from the repository root:

    python3 tools/make_og_card.py

Requires Pillow, like tools/optimize_images.py, and like that script it is run
by hand to regenerate a committed asset. Neither is part of the gate, and
neither runs on the deployed site.

The card is the hero photo the homepage already serves, cropped to the 1.91:1
that every unfurler expects, under the same rgba(0, 0, 0, 0.4) scrim that
css/style.css paints over the hero in .home-1:after, with the same two lines
of copy the hero carries. A shared link then previews as the top of the site
rather than as something assembled separately that can drift away from it.

JPEG, not PNG. The issue asked for a PNG, but this is a photograph: PNG is
lossless and would land near a megabyte at this size, five times the 200 KB
budget, and quantizing it down to fit would band the sky and the water badly.
Every unfurler accepts JPEG. tools/verify_seo_a11y.py asserts the dimensions
and the budget, so whichever format is used has to hold to both.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "img" / "hero-1280.jpg"
TARGET = ROOT / "img" / "og-card.jpg"

WIDTH, HEIGHT = 1200, 630
SCRIM = 0.4
BUDGET = 200 * 1024

# The page sets Lato, which is fetched from Google Fonts and is not on disk
# here. Open Sans is the closest humanist sans that is, and the fallbacks
# behind it are the two families present on essentially every Linux box. The
# card is generated once and committed, so this chain only has to resolve on
# whatever machine regenerates it.
FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def load_font(weight, size):
    for candidate in FONT_CANDIDATES[weight]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(
        "No %s font found. Install fonts-open-sans, or add a path to "
        "FONT_CANDIDATES." % weight
    )


def cover_crop(image, width, height):
    """Scale and center-crop to exactly width x height, preserving aspect.

    The source is 1280x853 (1.50:1) and the target is 1.91:1, so this crops
    off the top and bottom rather than squashing the horizon.
    """
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def main():
    if not SOURCE.exists():
        raise SystemExit("%s is missing; nothing to build the card from." % SOURCE)

    card = cover_crop(Image.open(SOURCE).convert("RGB"), WIDTH, HEIGHT)

    # Same scrim the hero carries, so the text has the same contrast on the
    # card that it has on the page.
    scrim = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    card = Image.blend(card, scrim, SCRIM)

    draw = ImageDraw.Draw(card)
    name_font = load_font("bold", 86)
    role_font = load_font("regular", 40)
    host_font = load_font("bold", 26)

    lines = [
        ("Brad Stricherz", name_font, (255, 255, 255), 236),
        ("Geospatial Software Engineer", role_font, (233, 233, 233), 350),
        ("GEOBRAD.DEV", host_font, (255, 255, 255), 430),
    ]
    for text, font, fill, top in lines:
        # Letter-space the wordmark the way the nav does, by drawing it with
        # spaces between characters rather than reaching for a layout engine.
        if font is host_font:
            text = " ".join(text)
        span = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((WIDTH - (span[2] - span[0])) / 2 - span[0], top),
            text,
            font=font,
            fill=fill,
        )

    card.save(TARGET, "JPEG", quality=82, optimize=True, progressive=True)

    size = TARGET.stat().st_size
    print("%s written: %dx%d, %.1f KB" % (TARGET.relative_to(ROOT), WIDTH, HEIGHT, size / 1024.0))
    if size >= BUDGET:
        print("Over the %d KB budget. Lower quality and rerun." % (BUDGET // 1024))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Generate the card**

Run: `python3 tools/make_og_card.py`
Expected: "img/og-card.jpg written: 1200x630, NNN.N KB" with the size under 200. If it is over, lower `quality` to 78 and rerun. Open the file and confirm the text is legible and the horizon is not cropped through the subject.

- [ ] **Step 5: Add the tags to index.html**

In `index.html`, after the canonical link added in Task 1, add:

```html
    <!-- Open Graph. Slack, LinkedIn, Bluesky, Discord, and iMessage all read
         these; Twitter reads twitter:card and falls back to og:* for the
         rest, so only the card type is repeated below. og:image must be
         absolute, because a crawler resolves a relative URL against its own
         base and silently ends up with no image. -->
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="GeoBrad.dev">
    <meta property="og:title" content="Brad Stricherz | Geospatial Software Engineer">
    <meta property="og:description" content="Open-source mapping and spatial analysis tools for nonprofits, researchers, and community organizers. React, Django, PostGIS, and CesiumJS.">
    <meta property="og:url" content="https://www.geobrad.dev/">
    <meta property="og:image" content="https://www.geobrad.dev/img/og-card.jpg">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="Brad Stricherz, Geospatial Software Engineer, over a photo of a wing foiler on open water">
    <meta name="twitter:card" content="summary_large_image">
```

- [ ] **Step 6: Teach verify_assets.py about the new asset**

In `tools/verify_assets.py`, add to `SHIPPED_VARIANTS` after `"img/qr_code-240.png"`:

```python
    # Never fetched by the page itself, only by link unfurlers, so it is not
    # in HOMEPAGE_ASSETS below. It is still an asset the markup names, and a
    # deleted or renamed one would 404 in every share.
    "img/og-card.jpg",
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python3 tools/verify_seo_a11y.py` and `python3 tools/verify_assets.py`
Expected: both print "All checks passed."

- [ ] **Step 8: Commit**

```bash
git add tools/make_og_card.py tools/verify_seo_a11y.py tools/verify_assets.py img/og-card.jpg index.html
git commit -m "feat: add a 1200x630 share card and the Open Graph tags that point at it"
```

---

### Task 3: Person structured data, and a JSON gate that can hold it

`verify_security.py` runs `node --check` over every inline `<script>` without a `src`. A JSON-LD block is data, not JavaScript, and node rejects it with "SyntaxError: Unexpected token ':'". The check has to learn the difference before the block can exist.

**Files:**
- Modify: `tools/verify_security.py:304-364`, `index.html` head, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `site_host`, `INDEX`, `HTML_PAGES` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
def json_ld_blocks(source):
    """Every <script type="application/ld+json"> body on the page, parsed.

    Returns a list of (raw, parsed) pairs, with parsed set to None when the
    block is not valid JSON, so the caller can report a broken block rather
    than raising on it.
    """
    blocks = []
    pattern = re.compile(
        r'<script\b[^>]*\btype\s*=\s*"application/ld\+json"[^>]*>(.*?)</script>',
        re.S | re.I,
    )
    for body in pattern.findall(source):
        try:
            blocks.append((body, json.loads(body)))
        except ValueError:
            blocks.append((body, None))
    return blocks


def check_homepage_has_person_structured_data():
    """Structured data has to describe what the page actually says.

    Google's guidelines are explicit that structured data must represent
    page content, so every field below is something a visitor can read on
    index.html: the name and title from the hero, the location and email
    from the contact block, the degree from the About copy, and the sameAs
    profiles from the two social lists. The employer named on resume.html is
    deliberately absent, because index.html never mentions it.
    """
    print("\nThe homepage carries Person structured data")

    source = read_or_fail(INDEX)
    if source is None:
        return

    host = site_host()
    if not check(host is not None, "CNAME names the site host"):
        return

    blocks = json_ld_blocks(source)
    if not check(bool(blocks), "index.html carries a JSON-LD block"):
        return

    for raw, parsed in blocks:
        check(parsed is not None, "index.html's JSON-LD parses as JSON")

    people = [parsed for _, parsed in blocks if isinstance(parsed, dict) and parsed.get("@type") == "Person"]
    if not check(bool(people), "index.html declares a Person"):
        return

    person = people[0]
    check(person.get("@context") == "https://schema.org", "the Person names the schema.org context")
    check(person.get("name", "").strip() != "", "the Person has a name")
    check(person.get("jobTitle", "").strip() != "", "the Person has a jobTitle")
    check(
        person.get("url") == "https://%s/" % host,
        "the Person's url is this site (%s)" % person.get("url"),
    )

    same_as = person.get("sameAs")
    check(
        isinstance(same_as, list) and len(same_as) >= 2,
        "the Person lists at least two sameAs profiles",
    )
    for url in same_as if isinstance(same_as, list) else []:
        check(
            isinstance(url, str) and url.startswith("https://"),
            "sameAs entry is an https URL (%s)" % url,
        )
        # A profile in sameAs that the page does not link is a claim nobody
        # can check, and one the page drops later goes stale silently.
        check(url in source, "sameAs entry is also linked from the page (%s)" % url)
```

Register it in `main()` after `check_homepage_carries_share_tags()`:

```python
    check_homepage_has_person_structured_data()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL on "index.html carries a JSON-LD block".

- [ ] **Step 3: Prove the security gate would reject JSON-LD before writing any**

Run:

```bash
printf '{\n  "@context": "https://schema.org"\n}\n' > /tmp/ld-probe.js
node --check /tmp/ld-probe.js
```

Expected: exit 1, "SyntaxError: Unexpected token ':'". This is what `verify_security.check_inline_script_syntax` would do to a JSON-LD block, and why the next step exists.

- [ ] **Step 4: Teach verify_security.py the difference between script and data**

In `tools/verify_security.py`, add `import json` beside the existing imports, then replace the body of `check_inline_script_syntax` from the `inline = re.compile(...)` line through the end of the function with:

```python
    # <script\s*> only matched an attribute-less tag, so <script type="module">
    # or <script defer> got no gate at all, and silently: a plain <script>
    # block elsewhere in the same file already satisfied the "has an inline
    # script to check" assertion below. Match any script tag without a src
    # attribute instead; a tag WITH src loads external code that this check
    # is not meant to see.
    inline = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S)

    # A script tag whose type is a data type holds data, not JavaScript.
    # node --check rejects a JSON-LD block outright ("Unexpected token ':'"),
    # so routing it to node would make structured data impossible to ship.
    # It still gets gated, just by the parser that matches what it is: a
    # malformed JSON-LD block is invisible to a search engine and worth
    # catching here exactly as a syntax error in the renderer is.
    data_type = re.compile(r'\btype\s*=\s*"(application/(?:ld\+)?json)"', re.I)
    tagged = re.compile(r"<script(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script>", re.S)

    # Iterating (INDEX, RESUME) exempted any page added later, which is the
    # same silent-exemption bug the HTML_PAGES glob was introduced to fix for
    # the other checks. Sweep every discovered page instead.
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        blocks = [
            (data_type.search(attrs), body) for attrs, body in tagged.findall(source)
        ]
        name = path.relative_to(ROOT)

        # index.html and resume.html are expected to carry inline script, so
        # finding none there means the extraction pattern broke rather than
        # that the script is gone. A page that legitimately has none,
        # thanks.html or the Termly privacy paste, must not fail for that.
        script_blocks = [body for kind, body in blocks if kind is None]
        if path in (INDEX, RESUME):
            if not check(bool(script_blocks), "%s has an inline script to check" % name):
                continue
        elif not blocks:
            print("  skip  %s has no inline script" % name)
            continue

        for number, (kind, body) in enumerate(blocks, start=1):
            if kind is not None:
                try:
                    json.loads(body)
                except ValueError as error:
                    fail(
                        "%s inline %s block %d is not valid JSON: %s"
                        % (name, kind.group(1), number, error)
                    )
                else:
                    print(
                        "  PASS  %s inline %s block %d parses"
                        % (name, kind.group(1), number)
                    )
                continue

            with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                result = subprocess.run(
                    ["node", "--check", handle.name],
                    capture_output=True,
                    text=True,
                )
            if result.returncode == 0:
                print("  PASS  %s inline script %d parses" % (name, number))
            else:
                fail(
                    "%s inline script %d is not valid JavaScript:\n%s"
                    % (name, number, result.stderr.strip())
                )
```

Also move the `node` availability guard so a missing `node` no longer skips the JSON blocks too. Replace:

```python
    if shutil.which("node") is None:
        print("  skip  node not found, cannot syntax-check inline scripts")
        return
```

with:

```python
    have_node = shutil.which("node") is not None
    if not have_node:
        print("  skip  node not found, JavaScript blocks go unchecked")
```

and guard the JavaScript branch with it, replacing the `with tempfile.NamedTemporaryFile(...)` block's opening line with:

```python
            if not have_node:
                continue
```

immediately before it.

- [ ] **Step 5: Add the JSON-LD to index.html**

In `index.html`, after the `twitter:card` meta added in Task 2, add:

```html
    <!-- Every field here is something the page itself states: the name and
         title from the hero, the email and location from the contact block,
         the degree from the About copy, and the profiles from the social
         lists. Structured data that outruns the page is what Google's
         guidelines call out, and it is also what goes stale first.

         verify_security.py routes this block to a JSON parser rather than to
         node --check, because node reads the first colon as a syntax error. -->
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Person",
      "name": "Brad Stricherz",
      "url": "https://www.geobrad.dev/",
      "image": "https://www.geobrad.dev/img/portrait-340.jpg",
      "jobTitle": "Geospatial Software Engineer",
      "email": "mailto:Brad@GeoBrad.dev",
      "telephone": "+1-605-270-0565",
      "address": {
        "@type": "PostalAddress",
        "addressLocality": "St. Louis",
        "addressRegion": "MO",
        "addressCountry": "US"
      },
      "alumniOf": {
        "@type": "CollegeOrUniversity",
        "name": "Pennsylvania State University"
      },
      "knowsAbout": [
        "Geographic Information Systems",
        "Spatial Data Science",
        "WebGIS",
        "PostGIS",
        "CesiumJS"
      ],
      "sameAs": [
        "https://github.com/GeoBradDev",
        "https://www.linkedin.com/in/brad-stricherz-944999349/",
        "https://bsky.app/profile/geobrad.bsky.social",
        "https://www.youtube.com/stricherz13",
        "https://www.instagram.com/GeoBradDev/",
        "https://www.facebook.com/brad.stricherz/"
      ]
    }
    </script>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tools/verify_seo_a11y.py` and `python3 tools/verify_security.py`
Expected: both print "All checks passed." `verify_security.py` must print a line reading "index.html inline application/ld+json block 1 parses", which is proof the new branch ran rather than the block being skipped.

- [ ] **Step 7: Prove the new gate actually catches broken JSON**

Temporarily delete the comma after `"name": "Brad Stricherz",` in the JSON-LD block, run `python3 tools/verify_security.py`, and confirm it FAILs with "is not valid JSON". Restore the comma and confirm it passes again. A gate nobody has seen fail is a gate nobody knows works.

- [ ] **Step 8: Commit**

```bash
git add tools/verify_security.py tools/verify_seo_a11y.py index.html
git commit -m "feat: add Person structured data, and gate JSON-LD with a JSON parser"
```

---

### Task 4: Accessible names for icon-only links and buttons

Twelve social links, the empty navbar brand, and the scroll-to-top button announce as "link" with no destination. The Font Awesome `<i>` elements inside them hold no text.

**Files:**
- Modify: `index.html:69`, `index.html:100`, `index.html:103`, `index.html:159-179`, `index.html:421-444`, `index.html:453-456`, `resume.html:334-425`, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `fail`, `read`, `HTML_PAGES` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
class AccessibleNames(HTMLParser):
    """Find an <a> or <button> that a screen reader would announce unnamed.

    An accessible name here comes from one of four places, which is what a
    browser's accname computation actually falls back through for these
    elements: aria-label on the element, aria-labelledby on it, text inside
    it, or the alt text of an image inside it. A Font Awesome <i> contributes
    nothing, because the glyph is a CSS ::before on an empty element.

    Also flags a decorative icon that is NOT hidden from assistive tech.
    Font Awesome 4 glyphs live in the Private Use Area, and a screen reader
    that reaches one announces whatever its character database says, which
    is at best nothing and at worst a wrong word ahead of the real name.
    """

    NAMED_BY = ("aria-label", "aria-labelledby", "title")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("a", "button"):
            named = any(attrs.get(key, "").strip() for key in self.NAMED_BY)
            # An <a> with no href is not a link and not focusable.
            interactive = tag == "button" or "href" in attrs
            self.stack.append(
                {"tag": tag, "named": named, "text": "", "line": self.getpos()[0],
                 "interactive": interactive}
            )
            return
        if tag == "img" and self.stack:
            if attrs.get("alt", "").strip():
                self.stack[-1]["text"] += attrs["alt"]
        if tag == "i" and "fa" in attrs.get("class", "").split():
            hidden = attrs.get("aria-hidden", "").lower() == "true"
            if not hidden:
                self.problems.append(
                    "line %d: decorative <i class=\"fa ...\"> is not aria-hidden"
                    % self.getpos()[0]
                )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"] += data

    def handle_endtag(self, tag):
        if tag not in ("a", "button") or not self.stack:
            return
        # Unwind to the matching open tag rather than assuming it is the top,
        # so one stray close tag does not desynchronize the whole page. Every
        # frame popped on the way is still judged: dropping them silently
        # would let an unnamed element escape by sitting under a mismatched
        # tag, which is exactly the malformed case worth reporting.
        while self.stack:
            frame = self.stack.pop()
            if frame["interactive"] and not frame["named"] and not frame["text"].strip():
                self.problems.append(
                    "line %d: <%s> has no accessible name" % (frame["line"], frame["tag"])
                )
            if frame["tag"] == tag:
                break


def check_images_have_alt_text():
    """An <img> with no alt announces its filename, or its URL.

    An empty alt is allowed and is the correct answer for a decorative
    image: it tells a screen reader to skip the image rather than guess at
    it. A missing attribute is not the same thing and is never correct.

    The filename check is the closest a source-level scan gets to "the alt
    is meaningful". It catches the copy-paste that puts portrait-340.jpg in
    the alt of portrait-340.jpg, which is the common way alt text ends up
    technically present and useless.
    """
    print("\nEvery image has alt text")

    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue

        tags = re.findall(r"<img\b[^>]*>", source, re.I)
        if not tags:
            print("  skip  %s has no <img>" % path.name)
            continue

        for tag in tags:
            src = re.search(r'\bsrc\s*=\s*"([^"]*)"', tag, re.I)
            label = src.group(1) if src else tag[:40]
            alt = re.search(r'\balt\s*=\s*"([^"]*)"', tag, re.I)
            if not check(alt is not None, "%s: <img src=%s> has an alt" % (path.name, label)):
                continue
            stem = label.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            check(
                alt.group(1).strip().lower() != stem,
                "%s: <img src=%s> alt is not just the filename" % (path.name, label),
            )


def check_interactive_elements_have_names():
    """A link announced as "link" tells a screen reader user nothing.

    Swept over every page, not just index.html, for the same reason
    verify_content.py sweeps every page for unclosed list items: the defect
    is not specific to the page it was first found on.
    """
    print("\nEvery link and button has an accessible name")

    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue

        parser = AccessibleNames()
        parser.feed(source)
        if parser.problems:
            for problem in parser.problems:
                fail("%s %s" % (path.name, problem))
        else:
            print("  PASS  %s names every link, button, and icon" % path.name)
```

Add `from html.parser import HTMLParser` to the imports, and register both checks in `main()`:

```python
    check_images_have_alt_text()
    check_interactive_elements_have_names()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL with exactly 36 problems on `index.html` and 11 on `resume.html`. `privacy.html` and `thanks.html` report 0 and pass; this was confirmed by dry-running the parser against the tree before this plan was written, so the 3,541-line Termly paste needs no edits. The alt check passes on every page as written; it is here to keep that true.

The 36 on `index.html` are 13 unnamed anchors and 23 unhidden icons. The anchors: the empty navbar brand (69), the hero scroll-down chevron (100), five icon-only social links in the About list (160, 163, 170, 172, 176), five more in the footer (423, 425, 434, 437, 441), and the scroll-to-top link (454). The two Bluesky links at 166 and 429 are already named by their `<img alt="Bluesky">` and do not appear. The 23 icons: three in the About contact list, five in the About social list, six service icons, three contact-item icons, five footer social icons, and the scroll-up chevron.

- [ ] **Step 3: Name the navbar brand**

In `index.html` line 69, replace:

```html
                <a class="navbar-brand effect" href="index.html"></a>
```

with:

```html
                <!-- Styled for a wordmark that was never filled in. Until one
                     is, the link still lands in the tab order and still needs
                     a name, or it announces as a bare "link" at the top of
                     every keyboard pass over the page. -->
                <a class="navbar-brand effect" href="index.html" aria-label="Brad Stricherz, home"></a>
```

- [ ] **Step 4: Name the social links and hide their icons**

In `index.html`, replace the `.social-list` block at lines 159 to 179 with:

```html
                    <ul class="social-list">
                        <li><a href="https://github.com/GeoBradDev" class="effect" target="_blank"
                               rel="noopener noreferrer" aria-label="GitHub"><i
                                class="fa fa-github" aria-hidden="true"></i></a>
                        </li>
                        <li><a href="https://www.facebook.com/brad.stricherz/" class="effect" target="_blank"
                               rel="noopener noreferrer" aria-label="Facebook"><i
                                class="fa fa-facebook" aria-hidden="true"></i></a></li>
                        <li>
                            <a href="https://bsky.app/profile/geobrad.bsky.social" class="effect" target="_blank"
                               rel="noopener noreferrer">
                                <img src="./img/Bluesky.svg" alt="Bluesky" width="16" height="16">
                            </a>
                        </li>
                        <li><a href="https://www.youtube.com/stricherz13" class="effect" target="_blank"
                               rel="noopener noreferrer" aria-label="YouTube"><i
                                class="fa fa-youtube" aria-hidden="true"></i></a>
                        </li>
                        <li><a href="https://www.instagram.com/GeoBradDev/" class="effect" target="_blank"
                               rel="noopener noreferrer" aria-label="Instagram"><i
                                class="fa fa-instagram" aria-hidden="true"></i></a>
                        </li>
                        <li><a href="https://www.linkedin.com/in/brad-stricherz-944999349/" class="effect"
                               target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"><i
                                class="fa fa-linkedin" aria-hidden="true"></i></a>
                        </li>
                    </ul>
```

Note that the Bluesky link needs no `aria-label`: the `<img alt="Bluesky">` inside it already supplies the name, and adding both would make the label win and the alt text dead.

- [ ] **Step 5: Name the footer social links and hide their icons**

In `index.html`, replace the `.footer-social-list` block at lines 422 to 444 with:

```html
                <ul class="footer-social-list">
                    <li><a class="effect" href="https://github.com/GeoBradDev" target="_blank"
                           rel="noopener noreferrer" aria-label="GitHub"><i
                            class="fa fa-github" aria-hidden="true"></i></a></li>
                    <li><a class="effect" href="https://www.facebook.com/brad.stricherz/" target="_blank"
                           rel="noopener noreferrer" aria-label="Facebook"><i
                            class="fa fa-facebook" aria-hidden="true"></i></a>
                    </li>
                    <li>
                        <a class="effect" href="https://bsky.app/profile/geobrad.bsky.social" target="_blank"
                           rel="noopener noreferrer">
                            <img src="./img/Bluesky.svg" alt="Bluesky" width="16" height="16">
                        </a>
                    </li>

                    <li><a class="effect" href="https://www.youtube.com/stricherz13" target="_blank"
                           rel="noopener noreferrer" aria-label="YouTube"><i
                            class="fa fa-youtube" aria-hidden="true"></i></a>
                    </li>
                    <li><a class="effect" href="https://www.instagram.com/GeoBradDev/" target="_blank"
                           rel="noopener noreferrer" aria-label="Instagram"><i
                            class="fa fa-instagram" aria-hidden="true"></i></a>
                    </li>
                    <li><a class="effect" href="https://www.linkedin.com/in/brad-stricherz-944999349/"
                           target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"><i
                            class="fa fa-linkedin" aria-hidden="true"></i></a>
                    </li>
                </ul>
```

- [ ] **Step 6: Name the scroll-to-top link, the hero chevron, and the photo credit**

In `index.html`, replace lines 453 to 456 with:

```html
<a href="#" class="scroll-up effect" aria-label="Back to top">
    <i class="fa fa-angle-up" aria-hidden="true"></i>
</a>
```

Replace line 100. This is the chevron under the hero headline; its only content is an empty `<span>` that CSS draws a dot into, so it announces as a bare link today:

```html
            <a href="#about" class="scroll home-s-btn hor-center" aria-label="Scroll to the about section"><span class="dot center"></span></a>
```

Replace line 103:

```html
            <p>Photo by <a href="https://www.mstudiowest.com/" target="_blank" rel="noopener noreferrer">Matthew McFarland</a></p>
```

- [ ] **Step 7: Hide the decorative icons in the About and Contact blocks**

In `index.html`, add `aria-hidden="true"` to each `<i class="fa ...">` that sits beside its own visible label and therefore names nothing: lines 143, 147, 153 in the About contact list, lines 237, 251, 265, 282, 295, 312 in the service icons, and lines 352, 363, 374 in the contact items. Each becomes, for example:

```html
                                    <span><i class="fa fa-envelope" aria-hidden="true"></i> Email : </span>
```

- [ ] **Step 8: Hide the decorative icons in resume.html**

In `resume.html`, add `aria-hidden="true"` to every `<i class="fa ... icon">`: the four in the contact line at 335 to 339, the map marker at 342, the six section headings at 348, 357, 368, 405, and 414, and the PDF icon at 425. The download link already has the visible text "Download PDF", so it needs no label.

- [ ] **Step 9: Run the test to verify it passes**

Run: `python3 tools/verify_seo_a11y.py`
Expected: "All checks passed."

- [ ] **Step 10: Run the rest of the gate**

Run `verify_assets.py`, `verify_security.py`, `verify_content.py`, and `verify_interactivity.py`. All exit 0. `verify_content.py`'s list-markup check is the one most likely to catch a mistake in the rewritten `<ul>` blocks above.

- [ ] **Step 11: Commit**

```bash
git add tools/verify_seo_a11y.py index.html resume.html
git commit -m "fix: give every icon-only link a name and hide the icons from assistive tech"
```

---

### Task 5: rel="noopener noreferrer" on every new-tab link

**Files:**
- Modify: `index.html`, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `fail`, `read`, `HTML_PAGES` from Task 1.

Most of these were already changed in Task 4. This task adds the check that keeps them that way and catches whatever Task 4 missed.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
def check_new_tab_links_carry_rel():
    """target="_blank" hands the new tab a window.opener back to this page.

    Every current browser implies noopener for target="_blank", so this is no
    longer the tabnabbing hole it was. It is still worth stating: the implicit
    behavior is a browser default rather than something this page asked for,
    noreferrer is not implied at all, and a reader of the markup should not
    have to know which browsers imply what.
    """
    print("\nEvery new-tab link states its rel")

    anchor = re.compile(r"<a\b[^>]*>", re.I)
    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue

        offenders = []
        for tag in anchor.findall(source):
            if not re.search(r'\btarget\s*=\s*"_blank"', tag, re.I):
                continue
            rel = re.search(r'\brel\s*=\s*"([^"]*)"', tag, re.I)
            if rel is None or "noopener" not in rel.group(1).lower():
                offenders.append(re.search(r'href\s*=\s*"([^"]*)"', tag))
        if offenders:
            for offender in offenders:
                fail(
                    "%s: target=_blank without rel=noopener (%s)"
                    % (path.name, offender.group(1) if offender else "no href")
                )
        else:
            print("  PASS  %s sets rel on every target=_blank link" % path.name)
```

Register it in `main()`.

Note: the anchors are written across multiple source lines in `index.html`, and this regex matches a tag across newlines because `[^>]*` spans them. Verified against the existing markup, where six of the twelve social anchors wrap.

- [ ] **Step 2: Run it to verify it fails or passes**

Run: `python3 tools/verify_seo_a11y.py`
Expected: PASS for `index.html` if Task 4 covered all thirteen, and PASS for `privacy.html`, whose Termly markup already carries `rel="noopener noreferrer"` on every one of its seventeen. If any FAIL lines appear, fix those anchors in `index.html` by adding `rel="noopener noreferrer"` beside the `target="_blank"`.

- [ ] **Step 3: Prove the check works by breaking it**

Temporarily remove `rel="noopener noreferrer"` from the GitHub link in the footer, rerun, and confirm one FAIL line naming that href. Restore it.

- [ ] **Step 4: Commit**

```bash
git add tools/verify_seo_a11y.py index.html
git commit -m "fix: state rel=noopener on every new-tab link rather than relying on the browser default"
```

---

### Task 6: Labels on the contact form

Placeholders vanish on focus, are not read by every screen reader as a name, and leave nothing above a filled field to say what it holds.

**Files:**
- Modify: `index.html:387-408`, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `fail`, `read_or_fail`, `INDEX` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
def check_form_controls_are_labelled():
    """A placeholder is a hint, not a name.

    It disappears the moment the field has content, which is exactly when a
    user tabbing back through a half-filled form needs to know what the field
    was. Every visible control needs a <label for>, an aria-label, or an
    aria-labelledby.

    The honeypot is deliberately exempt and deliberately named here rather
    than skipped by rule: it is display:none, so no user of any kind reaches
    it, and labelling it would advertise it to the bots it exists to catch.
    """
    print("\nEvery contact form control has a label")

    source = read_or_fail(INDEX)
    if source is None:
        return

    form = re.search(r'<form\b[^>]*id="contact-form".*?</form>', source, re.S)
    if not check(form is not None, "index.html has a contact form"):
        return
    form = form.group(0)

    labelled_for = set(re.findall(r'<label\b[^>]*\bfor\s*=\s*"([^"]+)"', form, re.I))

    controls = re.findall(r"<(input|textarea|select)\b[^>]*>", form, re.I)
    visible = 0
    for tag in controls:
        attrs = dict(re.findall(r'\b([\w-]+)\s*=\s*"([^"]*)"', tag))
        if attrs.get("type", "").lower() == "hidden":
            continue
        if "display:none" in attrs.get("style", "").replace(" ", ""):
            continue
        visible += 1

        identifier = attrs.get("id", "")
        named = (
            (identifier and identifier in labelled_for)
            or attrs.get("aria-label", "").strip()
            or attrs.get("aria-labelledby", "").strip()
        )
        check(
            bool(named),
            "the %s control is labelled" % (identifier or attrs.get("name") or tag[:40]),
        )

    check(visible >= 3, "the form still has its name, email, and message controls")

    # The FormSubmit wire contract. Renaming one of these does not break a
    # check anywhere else in the repo, it just quietly changes or drops a
    # field in the mail that arrives.
    for field in ("name", "email", "message", "_next", "_subject"):
        check(
            re.search(r'\bname\s*=\s*"%s"' % re.escape(field), form) is not None,
            "the form still posts a %s field" % field,
        )
```

Register it in `main()`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: three FAIL lines, one each for `name`, `email`, and `message`.

- [ ] **Step 3: Add the labels**

In `index.html`, replace lines 388 to 399 with:

```html
                    <div class="col-sm-6">
                        <!-- Visually hidden rather than absent. The design has
                             no room for three labels above three fields, but
                             the placeholder disappears as soon as the field
                             has content, which is exactly when a user tabbing
                             back through needs to know what it holds.
                             .sr-only is Bootstrap 3's, already loaded here. -->
                        <label for="name" class="sr-only">Your name</label>
                        <input type="text" name="name" id="name" class="input-field" required="required"
                               placeholder="Name">
                    </div>
                    <div class="col-sm-6">
                        <label for="email" class="sr-only">Your email address</label>
                        <input type="email" name="email" id="email" class="input-field" required="required"
                               placeholder="Email">
                    </div>
                    <div class="col-xs-12">
                        <label for="message" class="sr-only">Your message</label>
                        <textarea name="message" id="message" class="input-field" required="required"
                                  placeholder="Message"></textarea>
                    </div>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tools/verify_seo_a11y.py`
Expected: "All checks passed."

- [ ] **Step 5: Confirm the form spacing did not move**

`verify_content.py` asserts the three declarations that carry the form's spacing, because deleting the old error spans once collapsed the form from 387px to 289px. A `<label>` is `display: inline` by default and `.sr-only` takes it out of flow entirely, so the layout should be untouched.

Run: `python3 tools/verify_content.py`
Expected: exit 0. Confirm visually in Phase 6 that the form is still 387px tall at 1280px wide.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_seo_a11y.py index.html
git commit -m "fix: label the contact form fields instead of relying on placeholders"
```

---

### Task 7: Skip link and a visible focus indicator

`css/style.css:94` sets `outline: none` on `a, a:focus, a:hover, a:active`, and `.input-field` and `.submit-btn` each set it again. Every keyboard user on the site is navigating blind. A skip link is useless without a focus ring, so the two ship together.

**Files:**
- Modify: `css/style.css:94-98`, `css/style.css:1122-1160`, `index.html:44-56`, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `INDEX`, `STYLE_CSS` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
def check_skip_link_and_focus_visibility():
    """A skip link nobody can see is a skip link nobody can use.

    Two halves of one problem. The skip link has to be the first focusable
    thing in the document, or a keyboard user tabs through the whole nav
    before reaching the control that exists to let them skip the nav. And
    the stylesheet suppressed the focus ring site-wide, so even once the
    link takes focus there was nothing on screen to say so.

    :focus-visible rather than :focus on purpose. A mouse click on a link
    also focuses it, and an outline that appears on every click reads as a
    rendering bug, which is what led to outline: none in the first place.
    """
    print("\nThe skip link is first, and focus is visible")

    source = read_or_fail(INDEX)
    css = read_or_fail(STYLE_CSS)
    if source is None or css is None:
        return

    body = re.search(r"<body[^>]*>(.*)</body>", source, re.S | re.I)
    if not check(body is not None, "index.html has a body"):
        return

    first = re.search(r"<(?:a\b[^>]*\bhref|button|input|select|textarea)\b[^>]*>", body.group(1), re.I)
    if not check(first is not None, "index.html has a focusable element"):
        return
    check(
        "skip-link" in first.group(0),
        "the first focusable element is the skip link (found %s)" % first.group(0)[:60],
    )

    target = re.search(r'class="skip-link"[^>]*href="#([^"]+)"', source)
    if not target:
        target = re.search(r'href="#([^"]+)"[^>]*class="skip-link"', source)
    if check(target is not None, "the skip link targets a fragment"):
        check(
            re.search(r'id="%s"' % re.escape(target.group(1)), source) is not None,
            "the skip link's target #%s exists on the page" % target.group(1),
        )

    check(
        re.search(r"(?m)^\.skip-link\s*\{", css) is not None,
        "css/style.css styles .skip-link",
    )
    check(
        re.search(r"\.skip-link:focus", css) is not None,
        "css/style.css reveals .skip-link on focus",
    )

    # The blanket suppression, and its replacement. Matching the selector
    # list as written rather than any outline: none anywhere, because a
    # focus-visible rule is allowed to set outline on some other element.
    check(
        re.search(r"(?m)^a,\s*a:focus[^{]*\{[^}]*outline\s*:\s*none", css, re.S) is None,
        "css/style.css no longer strips the focus outline from every link",
    )
    check(
        css.count(":focus-visible") >= 3,
        "css/style.css declares :focus-visible outlines (found %d)"
        % css.count(":focus-visible"),
    )
```

Register it in `main()`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL on the skip link being absent, on `.skip-link` not being styled, and on the blanket `outline: none` still being present.

- [ ] **Step 3: Add the skip link to index.html**

In `index.html`, immediately after `<body>` on line 44 and before the loader, add:

```html
<!-- First focusable element in the document on purpose. Without it a keyboard
     user tabs the whole nav on every page load before reaching any content. -->
<a class="skip-link" href="#about">Skip to content</a>

```

The target is `#about` rather than `#home`, because `#home` is the hero and holds nothing to read; `#about` is the first section with content. `#about` already exists as a section id.

- [ ] **Step 4: Replace the blanket outline suppression in css/style.css**

Replace lines 94 to 98:

```css
a, a:focus, a:hover, a:active {
    text-decoration: none;
    color: inherit;
    outline: none;
}
```

with:

```css
a, a:focus, a:hover, a:active {
    text-decoration: none;
    color: inherit;
}

/* This rule used to read `outline: none` on the selector above, which took
   the focus ring off every link on the site and left keyboard users with no
   way to tell where they were. :focus-visible is what the browser uses to
   mean "focused, and the user is navigating by keyboard", so the ring comes
   back for them without appearing on every mouse click, which is the thing
   the blanket suppression was reaching for. */
a:focus-visible,
button:focus-visible,
input:focus-visible,
textarea:focus-visible,
select:focus-visible {
    outline: 2px solid #232323;
    outline-offset: 3px;
}

/* Over the hero photo and the dark footer, an outline in #232323 disappears.
   The same ring in white does not. */
.home-1 a:focus-visible,
.footer a:focus-visible,
.nav-wrapper a:focus-visible {
    outline-color: #fff;
}

/* Hidden until focused, then pinned to the top-left above the fixed header.
   z-index has to beat .nav-wrapper, or the link takes focus behind the nav
   and the user sees nothing. */
.skip-link {
    position: absolute;
    top: -100px;
    left: 12px;
    z-index: 200;
    padding: 10px 18px;
    background-color: #fff;
    color: #232323;
    font-weight: 700;
    transition: top .2s ease-in-out;
}

.skip-link:focus {
    top: 12px;
}

@media (prefers-reduced-motion: reduce) {
    .skip-link {
        transition: none;
    }
}
```

Note that `.skip-link:focus` is correct here rather than `:focus-visible`. The link is invisible until focused, so there is no mouse-click case to suppress: it cannot be clicked before it is shown.

- [ ] **Step 5: Drop the outline suppression on the form controls**

In `css/style.css`, remove the `outline: none;` line from the `.input-field` rule near line 1129 and from the `.submit-btn` rule near line 1155. Leave every other declaration in both rules exactly as it is; `verify_content.py` asserts `.input-field`'s `margin-bottom` and `.submit-btn`'s `clear`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tools/verify_seo_a11y.py` and `python3 tools/verify_content.py`
Expected: both print "All checks passed." / exit 0.

- [ ] **Step 7: Commit**

```bash
git add tools/verify_seo_a11y.py index.html css/style.css
git commit -m "fix: add a skip link and restore the keyboard focus ring the stylesheet suppressed"
```

---

### Task 8: robots.txt, sitemap.xml, and 404.html

**Files:**
- Create: `robots.txt`, `sitemap.xml`, `404.html`
- Modify: `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `read`, `read_or_fail`, `site_host`, `INDEXABLE`, `NOINDEX`, `ROOT` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`, and add `import xml.etree.ElementTree as ElementTree` to the imports:

```python
ROBOTS = ROOT / "robots.txt"
SITEMAP = ROOT / "sitemap.xml"
NOT_FOUND = ROOT / "404.html"

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def check_site_root_files():
    """The three files a crawler and a mistyped URL look for.

    The important assertion is the last one. A Disallow on a noindex page is
    the classic way to defeat your own noindex: the crawler is refused the
    file, so it never reads the tag that told it not to list the file, and
    the URL can still surface in results from inbound links alone.
    """
    print("\nrobots.txt, sitemap.xml, and 404.html")

    host = site_host()
    if not check(host is not None, "CNAME names the site host"):
        return

    robots = read(ROBOTS)
    if check(robots is not None, "robots.txt exists"):
        check(
            re.search(r"(?mi)^user-agent\s*:", robots) is not None,
            "robots.txt declares a User-agent",
        )
        check(
            "https://%s/sitemap.xml" % host in robots,
            "robots.txt points at the sitemap on %s" % host,
        )
        disallows = [
            value.strip()
            for value in re.findall(r"(?mi)^disallow\s*:(.*)$", robots)
            if value.strip()
        ]
        for page in sorted(NOINDEX):
            check(
                not any(page in rule for rule in disallows),
                "robots.txt does not Disallow %s, so its noindex stays readable" % page,
            )

    sitemap = read(SITEMAP)
    if check(sitemap is not None, "sitemap.xml exists"):
        try:
            root = ElementTree.fromstring(sitemap)
        except ElementTree.ParseError as error:
            fail("sitemap.xml is not well-formed XML: %s" % error)
        else:
            locations = [
                node.text.strip()
                for node in root.iter(SITEMAP_NS + "loc")
                if node.text
            ]
            check(bool(locations), "sitemap.xml lists at least one URL")
            for location in locations:
                check(
                    location.startswith("https://%s/" % host),
                    "sitemap entry is https and on %s (%s)" % (host, location),
                )
                # A sitemap is a request to index. Listing a noindex page
                # asks a crawler to do two contradictory things.
                page = location[len("https://%s/" % host):] or "index.html"
                check(
                    page not in NOINDEX,
                    "sitemap does not list the noindex page %s" % page,
                )
            for page in sorted(INDEXABLE):
                expected = "https://%s/" % host
                if page != "index.html":
                    expected = "https://%s/%s" % (host, page)
                check(expected in locations, "sitemap lists %s" % expected)

    source = read(NOT_FOUND)
    if check(source is not None, "404.html exists"):
        check(
            source.lstrip().lower().startswith("<!doctype html>"),
            "404.html opens with a doctype",
        )
        check(
            re.search(r'href="/"', source) is not None,
            "404.html links back to the site root",
        )
```

Register it in `main()`.

Note: `404.html` lands at the repo root, so `HTML_PAGES` picks it up and the Task 1 checks now apply to it too. It needs a description, a canonical, and an entry in `NOINDEX`.

- [ ] **Step 2: Add 404.html to the NOINDEX set**

In `tools/verify_seo_a11y.py`, change:

```python
NOINDEX = {"resume.html", "privacy.html", "thanks.html"}
```

to:

```python
NOINDEX = {"resume.html", "privacy.html", "thanks.html", "404.html"}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: FAIL on all three files being absent.

- [ ] **Step 4: Write robots.txt**

Create `robots.txt`:

```
# resume.html and privacy.html are deliberately kept out of search results,
# and they do that with a robots noindex in their own <head>, not from here.
# A Disallow would be worse than nothing: it stops a crawler fetching the
# page, so the crawler never reads the noindex, and the URL can still be
# listed from an inbound link alone. Allow everything; let the pages speak.
User-agent: *
Allow: /

Sitemap: https://www.geobrad.dev/sitemap.xml
```

- [ ] **Step 5: Write sitemap.xml**

Create `sitemap.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- One entry, because one page is meant to be found. resume.html is sent on
     request, privacy.html belongs to another project, thanks.html is a
     confirmation, and 404.html is an error page. All four carry a noindex,
     and listing a noindex page in a sitemap asks a crawler to do two
     contradictory things. No lastmod: there is no build step to keep one
     honest, and a stale lastmod is worse than an absent one. -->
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://www.geobrad.dev/</loc>
        <changefreq>monthly</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>
```

- [ ] **Step 6: Write 404.html**

Create `404.html`. GitHub Pages serves this for any unmatched path on the custom domain. It is standalone, like `thanks.html`, and carries its own copy of the four style rules it needs rather than pulling in Bootstrap for one panel:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>Page Not Found | Brad Stricherz</title>
    <meta name="description" content="That page does not exist on GeoBrad.dev. Head back to the homepage for geospatial software work, services, and contact details.">
    <link rel="canonical" href="https://www.geobrad.dev/404.html">

    <!-- An error page has nothing to offer a search result. -->
    <meta name="robots" content="noindex">

    <link href="https://fonts.googleapis.com/css?family=Lato:400,400i,700,700i" rel="stylesheet">
    <link rel="icon" href="img/favicon.ico">

    <style>
        /* Lifted from thanks.html, which lifted it from css/style.css: the
           55px rule is .s-line and the button is .submit-btn. Two standalone
           pages carrying the same forty lines beats either of them pulling in
           bootstrap.min.css and style.css for one panel. */
        body {
            margin: 0;
            padding: 30px;
            box-sizing: border-box;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Lato', sans-serif;
            font-size: 15px;
            font-weight: 400;
            line-height: 1.75;
            letter-spacing: 1px;
            background-color: #fff;
            color: #484848;
        }

        .panel {
            max-width: 480px;
            text-align: center;
        }

        h1 {
            margin: 0;
            font-size: 32px;
            font-weight: 700;
            line-height: 1.2;
            color: #333;
        }

        .rule {
            margin: 12px auto 0;
            width: 55px;
            height: 1px;
            background-color: #333;
        }

        p {
            margin: 22px 0 30px;
            font-size: 16px;
            line-height: 26px;
        }

        .back-btn {
            display: inline-block;
            padding: 8px 20px;
            font-size: 16px;
            font-weight: 700;
            text-decoration: none;
            border: 2px solid #333;
            background-color: #333;
            color: #fafafa;
            transition: all .4s ease-in-out;
        }

        .back-btn:hover {
            color: #111;
            background-color: transparent;
        }

        /* Keyboard users get an outline the hover state cannot supply, and it
           has to sit outside the border to stay visible against the fill. */
        .back-btn:focus-visible {
            outline: 2px solid #333;
            outline-offset: 3px;
        }

        @media (prefers-reduced-motion: reduce) {
            .back-btn {
                transition: none;
            }
        }
    </style>
</head>
<body>

<div class="panel">
    <h1>Page not found</h1>
    <div class="rule"></div>
    <p>That URL does not lead anywhere on this site. It may have moved, or the link that sent you here may be wrong.</p>
    <a class="back-btn" href="/">Back to GeoBrad.dev</a>
</div>

</body>
</html>
```

- [ ] **Step 7: Run the whole gate**

Run all five verifiers. Every one exits 0.

`404.html` is now swept by `verify_assets.py` (no `<img>`, so it prints a skip line), `verify_security.py` (no inline script, so it prints a skip line; no `http://` asset), `verify_content.py` (no list items), and every Task 1 check in `verify_seo_a11y.py`.

- [ ] **Step 8: Commit**

```bash
git add robots.txt sitemap.xml 404.html tools/verify_seo_a11y.py
git commit -m "feat: add robots.txt, sitemap.xml, and a custom 404 page"
```

---

### Task 9: Text contrast

`.portfolio-stars` sets `#6c757d` on `#f8f9fa`, which computes to 4.45:1 against the WCAG AA threshold of 4.5:1 for body text. The same gray on the white card is 4.69:1 and passes, but only just.

**Files:**
- Modify: `index.html` embedded portfolio CSS, `tools/verify_seo_a11y.py`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `INDEX` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_seo_a11y.py`, above `main()`:

```python
# Text colors and the background each is actually painted on, for the
# portfolio cards built by the inline renderer in index.html. The pair cannot
# be derived from the CSS alone: .portfolio-description p declares only a
# color, and the white behind it comes from .portfolio-card several levels
# up. So the background is named here and the foreground is read out of the
# file, which is the half that changes.
#
# AA is 4.5:1 for body text. Every pair below is body text: the largest is
# 14px, well under the 18.66px bold / 24px regular that would qualify for the
# 3:1 large-text threshold.
CONTRAST_PAIRS = [
    (".portfolio-title", "#ffffff"),
    (".portfolio-description p", "#ffffff"),
    (".portfolio-stars", None),      # declares its own background
    (".portfolio-language", None),   # declares its own background
    (".portfolio-link-code", "#ffffff"),
    (".portfolio-link-demo", None),  # declares its own background
]
CONTRAST_MINIMUM = 4.5


def channel_luminance(value):
    """One sRGB channel, 0-255, linearized per WCAG 2.x."""
    channel = value / 255.0
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    """WCAG relative luminance of a #rrggbb string."""
    color = color.lstrip("#")
    red, green, blue = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return (
        0.2126 * channel_luminance(red)
        + 0.7152 * channel_luminance(green)
        + 0.0722 * channel_luminance(blue)
    )


def contrast_ratio(foreground, background):
    first = relative_luminance(foreground)
    second = relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def rule_body(source, selector):
    """The declaration block of the rule opening exactly at `selector`."""
    match = re.search(
        r"(?m)^%s\s*\{(.*?)\}" % re.escape(selector), source, re.S
    )
    return match.group(1) if match else None


def declared_color(body, prop):
    """A #rrggbb or #rgb value for `prop` in a declaration block, expanded."""
    match = re.search(r"(?<![-\w])%s\s*:\s*(#[0-9a-fA-F]{3,6})" % prop, body)
    if not match:
        return None
    value = match.group(1)
    if len(value) == 4:
        value = "#" + "".join(char * 2 for char in value[1:])
    return value.lower()


def check_text_contrast():
    """Computed, not asserted, so changing a color rechecks it.

    Only the portfolio card palette, which is where the borderline values
    are. The rest of the site is #232323, #333, or #484848 on white, all of
    them above 8:1, and a general cascade-resolving checker is what Lighthouse
    and axe are for. Phase 6 runs both against the real page.
    """
    print("\nCard text meets the AA contrast threshold")

    source = read_or_fail(INDEX)
    if source is None:
        return

    for selector, assumed_background in CONTRAST_PAIRS:
        body = rule_body(source, selector)
        if not check(body is not None, "index.html styles %s" % selector):
            continue

        foreground = declared_color(body, "color")
        if not check(foreground is not None, "%s declares a text color" % selector):
            continue

        background = declared_color(body, "background") or assumed_background
        if not check(
            background is not None,
            "%s has a known background to measure against" % selector,
        ):
            continue

        ratio = contrast_ratio(foreground, background)
        check(
            ratio >= CONTRAST_MINIMUM,
            "%s is %.2f:1 (%s on %s), at or above %.1f:1"
            % (selector, ratio, foreground, background, CONTRAST_MINIMUM),
        )
```

Register it in `main()`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_seo_a11y.py`
Expected: one FAIL reading ".portfolio-stars is 4.45:1 (#6c757d on #f8f9fa), at or above 4.5:1", and PASS for the other five.

- [ ] **Step 3: Darken the gray**

In `index.html`, replace every `#6c757d` in the embedded portfolio CSS with `#5a6268`. There are four occurrences: `.portfolio-stars`, `.portfolio-description p`, `.portfolio-link-code`, and `.portfolio-loading`. Change all four rather than only the failing one, so the card palette stays one gray instead of two that differ by an amount nobody can see but a checker can.

`#5a6268` computes to 5.89:1 on `#f8f9fa` and 6.21:1 on white, which clears AA with room for a future background tweak rather than sitting on the line.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 tools/verify_seo_a11y.py`
Expected: "All checks passed.", with `.portfolio-stars` now reporting 5.89:1.

- [ ] **Step 5: Prove the checker computes rather than asserts**

Temporarily change `.portfolio-stars`'s color to `#8a9298`, rerun, and confirm the FAIL line reports a different, lower ratio than before. Restore `#5a6268`.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_seo_a11y.py index.html
git commit -m "fix: darken the card gray so the star count clears the AA contrast threshold"
```

---

## Spec coverage

| Issue 19 acceptance criterion | Task |
|---|---|
| Every page has a unique meta description, canonical URL, and OG/Twitter tags | 1, and 2 for the cards |
| A purpose-built 1200x630 OG image exists and is under 200 KB | 2 |
| `robots.txt`, `sitemap.xml`, and `404.html` exist | 8 |
| `Person` JSON-LD on the homepage | 3 |
| Every image has meaningful alt text | 4 (already true; the check is what keeps it true) |
| Every icon-only link and button has an accessible name | 4 |
| All form inputs have labels | 6 |
| Skip-to-content link present | 7 |
| Lighthouse accessibility and SEO above 95 | Phase 6 of the /work-issue run |

Findings in the issue body that need no work, and why:

- Stronger `<title>` tags, and the portrait's missing `alt`, were both fixed by issue 15. Task 1 still changes `resume.html`'s title, because it was a byte-for-byte copy of `index.html`'s.
- The custom scroll hijacking in `js/main.js` was deleted by issue 16. The issue itself calls this a "do not restore this part" note, and `CLAUDE.md` already carries that rule.

Two deliberate deviations from the issue text, both to be repeated in the PR body:

1. **OG and Twitter cards go on `index.html` only,** not on all four pages. The owner's answer during Phase 1 was to keep `resume.html` and `privacy.html` out of search entirely, which is the search-engine half of the decision issue 18 recorded. A share card on a page nobody is meant to share is markup that can only go stale, so Task 2 asserts the other three pages carry no `og:url`.
2. **The share card is JPEG, not PNG.** The issue says PNG. The card is a photograph, and lossless PNG at 1200x630 lands near a megabyte, five times the issue's own 200 KB budget; quantizing to fit would band the sky and water. Every unfurler accepts JPEG. The dimensions and the budget, which are the parts that matter, are both asserted.

## Verification

After every task, all five verifiers exit 0:

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_content.py
python3 tools/verify_interactivity.py
python3 tools/verify_seo_a11y.py
```

Phase 6 of the /work-issue run adds the runtime half these source-level checks cannot cover, since the issue's own acceptance criterion is a Lighthouse score:

1. Serve the site with `python3 -m http.server 8000` and drive `index.html` in a real browser.
2. Run Lighthouse for accessibility and SEO. Both must score above 95.
3. Tab from the top of the page and confirm the skip link appears, is readable, and lands on `#about`.
4. Confirm the contact form still measures 387px tall at 1280px wide.
5. Confirm a mistyped path serves `404.html` (GitHub Pages behavior; locally, load `/404.html` directly).
6. Open `img/og-card.jpg` and confirm the text is legible and the crop is not through the subject.
