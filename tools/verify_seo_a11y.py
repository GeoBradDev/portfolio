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
    except the three that are not frame headers) carries height then width as
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

    Only index.html carries these. The other pages are noindex and unlinked,
    and a card on a page nobody is meant to share is markup that can only
    ever go stale.

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
    check(
        card == "summary_large_image",
        "index.html sets twitter:card to summary_large_image",
    )

    # The pages that are not meant to be shared must not carry a card that
    # would rot. This is the check that keeps a future copy-paste of the
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


def main():
    check_every_page_is_a_complete_document()
    check_every_page_has_a_description()
    check_every_page_declares_a_canonical()
    check_indexing_policy_is_explicit()
    check_share_card_exists_and_fits()
    check_homepage_carries_share_tags()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
