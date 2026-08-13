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
