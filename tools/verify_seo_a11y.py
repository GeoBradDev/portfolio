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

Issue 31 replaced Font Awesome with inline SVG and Bootstrap with local CSS,
and the checks here followed. AccessibleNames fails a leftover Font Awesome
<i> or <span> and any <svg> not aria-hidden="true" focusable="false", and
check_renderer_icons_are_hidden holds the same rule over the SVGs the
portfolio renderer creates. check_no_bootstrap_classes fails a Bootstrap grid,
utility, component, or collapse class or data attribute anywhere, including
renderer string literals, and requires a local rule for each Bootstrap-named
class the site kept. The skip-link check no longer asserts the
a:focus:not(:focus-visible) rule that only existed to beat Bootstrap; it
asserts that nothing paints an outline or box-shadow on plain :focus.
"""

import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RESUME = ROOT / "resume.html"
PRIVACY = ROOT / "privacy.html"
THANKS = ROOT / "thanks.html"
STYLE_CSS = ROOT / "css" / "style.css"
CNAME = ROOT / "CNAME"
ROBOTS = ROOT / "robots.txt"
SITEMAP = ROOT / "sitemap.xml"
NOT_FOUND = ROOT / "404.html"

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# Portfolio card text, as (selector, background when the rule declares none).
# The cards are built by the inline renderer in index.html, but issue 20 moved
# their CSS out of a JavaScript string in that file and into style.css, so this
# reads the stylesheet the way check_focus_ring_contrast already does.
CONTRAST_PAIRS = [
    (".portfolio-title", "#ffffff"),
    (".portfolio-description p", "#ffffff"),
    (".portfolio-stars", None),      # declares its own background
    (".portfolio-language", None),   # declares its own background
    (".portfolio-link-code", "#ffffff"),
    (".portfolio-link-demo", None),  # declares its own background
    (".portfolio-error", None),      # declares its own background
    # The renderer's empty state. It sits on #portfolio's gradient, which runs
    # from #f8f9fa to #e9ecef; measured against the darker end, so the ratio
    # holds anywhere on it. Not declared on the rule, because a solid
    # background would paint a box over the gradient that was never there.
    (".portfolio-empty", "#e9ecef"),
]
CONTRAST_MINIMUM = 4.5

# WCAG 2.2 SC 1.4.11 non-text contrast. A focus indicator is its canonical
# example, and it is a lower bar than the 4.5:1 body text needs.
FOCUS_RING_MINIMUM = 3.0

# Every page at the repo root, discovered from the filesystem rather than
# hardcoded, so a page added later is covered instead of silently exempt.
# Same rule verify_assets.py, verify_security.py, and verify_content.py use.
HTML_PAGES = sorted(ROOT.glob("*.html"))

# Which pages search engines may list. Anything not named here must carry a
# robots noindex. A page added later lands in neither set and fails the
# "every page states an indexing policy" check, which is the point: the
# decision gets made deliberately rather than by default.
INDEXABLE = {"index.html"}
NOINDEX = {"resume.html", "privacy.html", "thanks.html", "404.html"}

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


def without_comments(source, style):
    """Strip comments so a scan reads code, not prose about code.

    Same helper, and the same reason, as verify_content.without_comments and
    verify_assets.without_comments. Every regex scan below reads raw markup,
    and a comment has to quote the thing it explains: the comment in
    index.html describing why the Bluesky links carry no aria-label contains
    the text of an img tag, and this file reported it as a real image before
    the strip was added.

    AccessibleNames does not need this. HTMLParser routes comments to
    handle_comment, which it does not implement, so they never reach the
    element handlers.
    """
    pattern = r"/\*.*?\*/" if style == "css" else r"<!--.*?-->"
    return re.sub(pattern, "", source, flags=re.S)


def read_markup(path):
    """read(), with HTML comments stripped. See without_comments."""
    source = read(path)
    return None if source is None else without_comments(source, "html")


def read_markup_or_fail(path):
    """read_markup(), plus one FAIL line for a missing file instead of None."""
    text = read_markup(path)
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
        source = read_markup(path)
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
        source = read_markup(path)
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
        source = read_markup(path)
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
        source = read_markup(path)
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

    source = read_markup_or_fail(INDEX)
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
        other = read_markup(path)
        if other is None:
            continue
        check(
            meta_content(other, property="og:url") is None,
            "%s carries no og:url to go stale" % path.name,
        )


def json_ld_blocks(source):
    """Every <script type="application/ld+json"> body on the page, parsed.

    Returns a list of (raw, parsed) pairs, with parsed set to None when the
    block is not valid JSON, so the caller can report a broken block rather
    than raising on it.
    """
    blocks = []
    pattern = re.compile(
        r'<script\b[^>]*\btype\s*=\s*"application/ld\+json"[^>]*>(.*?)</script(?=[\s/>])[^>]*>',
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

    source = read_markup_or_fail(INDEX)
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

    people = [
        parsed
        for _, parsed in blocks
        if isinstance(parsed, dict) and parsed.get("@type") == "Person"
    ]
    if not check(bool(people), "index.html declares a Person"):
        return

    person = people[0]
    check(
        person.get("@context") == "https://schema.org",
        "the Person names the schema.org context",
    )
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


class AccessibleNames(HTMLParser):
    """Find an <a> or <button> that a screen reader would announce unnamed.

    An accessible name here comes from one of four places, which is what a
    browser's accname computation actually falls back through for these
    elements: aria-label on the element, aria-labelledby on it, text inside
    it, or the alt text of an image inside it. An icon contributes nothing:
    every icon on the site is an inline <svg> that is hidden from assistive
    tech, so a link whose only content is one still needs its own name.

    Also flags two icon defects. Any <svg> that is not both
    aria-hidden="true" and focusable="false": an unhidden SVG is announced
    as an unlabelled graphic ahead of the real name, and focusable="false"
    keeps the legacy engines that made SVGs tab stops from adding one. And
    any <i> or <span> still carrying a Font Awesome class (fa, fa-*): issue
    31 removed Font Awesome, so such an element renders as nothing at all
    and its icon has silently disappeared.
    """

    NAMED_BY = ("aria-label", "aria-labelledby", "title")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("a", "button"):
            named = any((attrs.get(key) or "").strip() for key in self.NAMED_BY)
            # An <a> with no href is not a link and not focusable.
            interactive = tag == "button" or "href" in attrs
            self.stack.append(
                {
                    "tag": tag,
                    "named": named,
                    "text": "",
                    "line": self.getpos()[0],
                    "interactive": interactive,
                }
            )
            return
        if tag == "img" and self.stack:
            if (attrs.get("alt") or "").strip():
                self.stack[-1]["text"] += attrs["alt"]
        classes = (attrs.get("class") or "").split()
        if tag in ("i", "span") and any(
            token == "fa" or token.startswith("fa-") for token in classes
        ):
            self.problems.append(
                "line %d: <%s class=\"%s\"> is a Font Awesome icon, and Font "
                "Awesome is no longer loaded, so it renders nothing"
                % (self.getpos()[0], tag, " ".join(classes))
            )
        if tag == "svg":
            if (attrs.get("aria-hidden") or "").lower() != "true":
                self.problems.append(
                    'line %d: <svg> is not aria-hidden="true"' % self.getpos()[0]
                )
            if (attrs.get("focusable") or "").lower() != "false":
                self.problems.append(
                    'line %d: <svg> is not focusable="false"' % self.getpos()[0]
                )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"] += data

    def judge(self, frame):
        if frame["interactive"] and not frame["named"] and not frame["text"].strip():
            self.problems.append(
                "line %d: <%s> has no accessible name" % (frame["line"], frame["tag"])
            )

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
            self.judge(frame)
            if frame["tag"] == tag:
                break

    def finish(self):
        """Judge whatever never closed.

        An element that opens and never closes leaves its frame on the stack,
        and handle_endtag only judges frames it pops. Without this, adding
        <a href="/x"> holding only a hidden icon, with no </a>, ships an
        unnamed link past a green gate. Verified: the same markup with the
        closing tag was reported, and without it was not.
        """
        while self.stack:
            self.judge(self.stack.pop())
        return self.problems


def check_images_have_alt_text():
    """An <img> with no alt announces its filename, or its URL.

    An empty alt is allowed and is the correct answer for a decorative
    image: it tells a screen reader to skip the image rather than guess at
    it. A missing attribute is not the same thing and is never correct.

    The filename check is the closest a source-level scan gets to "the alt
    is meaningful". It catches the copy-paste that puts portrait-340.jpg, or
    portrait-340, in the alt of portrait-340.jpg.

    It deliberately does not fire when the alt matches a filename that is a
    single plain word, because a logo file named after the brand it depicts
    is the normal case and the brand is the correct alt text. Bluesky.svg
    with alt="Bluesky" is right, and an earlier version of this check called
    it wrong. Only a stem carrying a digit or a separator, which is what a
    generated or size-suffixed asset name looks like, counts as a filename
    leaking into the alt.
    """
    print("\nEvery image has alt text")

    machine_name = re.compile(r"[\d_-]")
    for path in HTML_PAGES:
        source = read_markup(path)
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
            if not check(
                alt is not None, "%s: <img src=%s> has an alt" % (path.name, label)
            ):
                continue

            text = alt.group(1).strip().lower()
            basename = label.rsplit("/", 1)[-1].lower()
            stem = basename.rsplit(".", 1)[0]
            leaked = text == label.lower() or text == basename or (
                text == stem and machine_name.search(stem) is not None
            )
            check(
                not leaked,
                "%s: <img src=%s> alt is not the filename" % (path.name, label),
            )


def check_interactive_elements_have_names():
    """A link announced as "link" tells a screen reader user nothing.

    Swept over every page, not just index.html, for the same reason
    verify_content.py sweeps every page for unclosed list items: the defect
    is not specific to the page it was first found on.
    """
    print("\nEvery link and button has an accessible name")

    for path in HTML_PAGES:
        source = read_markup(path)
        if source is None:
            continue

        parser = AccessibleNames()
        parser.feed(source)
        parser.finish()
        if parser.problems:
            for problem in parser.problems:
                fail("%s %s" % (path.name, problem))
        else:
            print("  PASS  %s names every link, button, and icon" % path.name)


def inline_scripts(source):
    """Bodies of every inline <script> that holds JavaScript, not data."""
    tagged = re.compile(r"<script(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script(?=[\s/>])[^>]*>", re.S | re.I)
    data = re.compile(r'\btype\s*=\s*"application/(?:ld\+)?json"', re.I)
    return [body for attrs, body in tagged.findall(source) if not data.search(attrs)]


def strip_js_comments(code):
    """JavaScript with its /* */ and // comments removed, strings intact.

    Quote-aware: a // or /* inside a string literal, such as "https://..."
    or a path with a doubled slash, is part of the string and is kept. A
    comment that quotes code, such as `// icon(name) returns an inline
    <svg>`, is gone before any scan reads the code. Regular expression
    literals are not recognized; the scripts here have none that hold a
    quote or a //.
    """
    out = []
    index, length = 0, len(code)
    quote = None
    while index < length:
        char = code[index]
        if quote:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(code[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if code.startswith("/*", index):
            end = code.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        if code.startswith("//", index):
            end = code.find("\n", index)
            index = length if end == -1 else end
            continue
        out.append(char)
        index += 1
    return "".join(out)


class MarkupFacts(HTMLParser):
    """Class tokens, stylesheet links, and inline styles, read by a real parser.

    Regexes for class="..." and href="css/..." missed single-quoted and
    unquoted attributes and root-absolute hrefs.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.classes = []
        self.sheets = []
        self.styles = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or "") for key, value in attrs}
        self.classes.extend(attr.get("class", "").split())
        if tag == "link" and "stylesheet" in attr.get("rel", "").lower().split():
            self.sheets.append(attr.get("href", "").strip())
        if tag == "style":
            self._in_style = True
            self.styles.append("")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self._in_style = False

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles[-1] += data


def markup_facts(source):
    facts = MarkupFacts()
    facts.feed(source)
    facts.close()
    return facts


def local_sheet(href):
    """The repo path a first-party stylesheet href names, or None if off-site."""
    if re.match(r"\s*(?:[a-z][a-z0-9+.-]*:|//)", href, re.I):
        return None
    path = ROOT / re.sub(r"^(?:\./|/)", "", href.split("?")[0].split("#")[0])
    return path if path.is_file() else None


def check_renderer_icons_are_hidden():
    """The portfolio cards build their icons at runtime, out of the parser's reach.

    AccessibleNames reads the markup as shipped, and the star, Live Demo, and
    Code icons on every card do not exist until the inline renderer in
    index.html creates them. So this reads the renderer instead. Its icons
    have to be real SVG elements, which only createElementNS with the SVG
    namespace makes (createElement("svg") makes an HTMLUnknownElement that
    draws nothing), and the helper that makes them has to set aria-hidden
    and focusable on what it creates, for the same reasons the static rule
    gives.
    """
    print("\nThe portfolio renderer builds hidden SVG icons")

    source = read_markup_or_fail(INDEX)
    if source is None:
        return
    script = strip_js_comments("\n".join(inline_scripts(source)))

    # Any namespace argument: a literal, or a constant holding it. The local
    # name "svg" is what makes the element an <svg>.
    site = re.compile(r"createElementNS\(\s*[^,()]+,\s*([\"'])svg\1\s*\)")
    sites = list(site.finditer(script))
    if not check(
        bool(sites),
        "the renderer creates its icons with createElementNS in the SVG namespace",
    ):
        return

    # Every site, not the first, and the attributes bound to the variable the
    # <svg> is assigned to: setting them on the <use> inside, or on any other
    # element, hides nothing the screen reader sees as the graphic. The
    # search runs from the site to the next function definition, which is
    # the scope the helper works in.
    for number, match in enumerate(sites, start=1):
        assigned = re.search(
            r"(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*=\s*(?:[A-Za-z_$][\w$]*\s*\.\s*)*$",
            script[:match.start()],
        )
        if not check(
            assigned is not None,
            "renderer SVG %d is assigned to a variable, so its attributes can be checked" % number,
        ):
            continue
        name = assigned.group(1)
        following = re.search(r"\bfunction\b", script[match.end():])
        scope = script[match.end():match.end() + following.start() if following else len(script)]
        for attribute, value in (("aria-hidden", "true"), ("focusable", "false")):
            check(
                re.search(
                    r"(?<![\w$.])%s\.setAttribute(?:NS\(\s*(?:null|\"\"|'')\s*,|\()"
                    r"\s*([\"'])%s\1\s*,\s*(?:([\"'])%s\2|%s)\s*\)"
                    % (re.escape(name), re.escape(attribute), value, value),
                    scope,
                )
                is not None,
                'renderer SVG %d sets %s="%s" on the <svg> itself (%s)'
                % (number, attribute, value, name),
            )


def check_new_tab_links_carry_rel():
    """target="_blank" hands the new tab a window.opener back to this page.

    Every current browser implies noopener for target="_blank", so this is no
    longer the tabnabbing hole it was. It is still worth stating: the implicit
    behavior is a browser default rather than something this page asked for,
    noreferrer is not implied at all, and a reader of the markup should not
    have to know which browsers imply what.

    The anchors in index.html wrap across source lines, and [^>]* spans
    newlines, so a multi-line tag is matched whole rather than missed.
    """
    print("\nEvery new-tab link states its rel")

    anchor = re.compile(r"<a\b[^>]*>", re.I)
    for path in HTML_PAGES:
        source = read_markup(path)
        if source is None:
            continue

        offenders = []
        for tag in anchor.findall(source):
            if not re.search(r'\btarget\s*=\s*"_blank"', tag, re.I):
                continue
            rel = re.search(r'\brel\s*=\s*"([^"]*)"', tag, re.I)
            if rel is None or "noopener" not in rel.group(1).lower():
                offenders.append(re.search(r'href\s*=\s*"([^"]*)"', tag, re.I))
        if offenders:
            for offender in offenders:
                fail(
                    "%s: target=_blank without rel=noopener (%s)"
                    % (path.name, offender.group(1) if offender else "no href")
                )
        else:
            print("  PASS  %s sets rel on every target=_blank link" % path.name)


def check_form_controls_are_labelled():
    """A placeholder is a hint, not a name.

    It disappears the moment the field has content, which is exactly when a
    user tabbing back through a half-filled form needs to know what the field
    was. Every visible control needs a <label for>, an aria-label, or an
    aria-labelledby.

    The honeypot is deliberately exempt and deliberately skipped by shape
    rather than by name: it is display:none, so no user of any kind reaches
    it, and labelling it would advertise it to the bots it exists to catch.
    """
    print("\nEvery contact form control has a label")

    source = read_markup_or_fail(INDEX)
    if source is None:
        return

    form = re.search(r'<form\b[^>]*id="contact-form".*?</form>', source, re.S)
    if not check(form is not None, "index.html has a contact form"):
        return
    form = form.group(0)

    labelled_for = set(re.findall(r'<label\b[^>]*\bfor\s*=\s*"([^"]+)"', form, re.I))

    controls = re.findall(r"<(?:input|textarea|select)\b[^>]*>", form, re.I)
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


ZERO_LENGTH = re.compile(r"[-+]?0*\.?0+(?:[a-z%]+)?")
LENGTH = re.compile(r"[-+]?\d*\.?\d+(?:[a-z%]+)?")
COLOR_FUNCTIONS = {
    "rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch", "color",
}


def css_tokens(value):
    """Top-level tokens of a CSS value, a function call kept whole.

    rgb(0 0 0) is one token, not three zeros. Splitting on whitespace alone
    read the components of a color as zero widths and passed a visible ring.
    """
    tokens, current, depth = [], "", 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char.isspace() and depth == 0:
            if current:
                tokens.append(current)
            current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def split_top_level(value, separator=","):
    """value split at separators outside any parentheses."""
    parts, current, depth = [], "", 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == separator and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def invisible_color(token):
    """True for transparent and for a color function whose alpha is zero.

    A fully transparent alpha, rgb(0 0 0 / 0) or rgba(0, 0, 0, 0), paints
    nothing, exactly like the keyword. var() is unknown here and counts as
    visible.
    """
    if token == "transparent":
        return True
    match = re.fullmatch(r"([a-z-]+)\((.*)\)", token)
    if not match or match.group(1) not in COLOR_FUNCTIONS:
        return False
    inner = match.group(2)
    if "/" in inner:
        alpha = inner.rsplit("/", 1)[1].strip()
    else:
        parts = [part.strip() for part in split_top_level(inner)]
        if len(parts) != 4:
            return False
        alpha = parts[3]
    return re.fullmatch(r"[-+]?0*\.?0+%?", alpha) is not None


def is_length(token):
    """A width or offset token: a number with a unit, or a bare number."""
    return LENGTH.fullmatch(token) is not None


def paints_ring(prop, value, body):
    """Whether a focus declaration paints anything in normal rendering.

    An outline paints nothing when its style is none or hidden, its width is
    zero, or its color is transparent or has zero alpha (the forced-colors
    technique, which shows only when the OS replaces colors). A box-shadow
    list paints nothing when every shadow in it is invisible in color or has
    no offset, blur, or spread. Values are tokenized with color functions and
    var() kept whole, so only a real width can read as zero.
    """
    tokens = css_tokens(value)
    if prop.startswith("outline"):
        color = re.search(r"(?<![-\w])outline-color\s*:\s*([^;}]+)", body)
        if color:
            declared = css_tokens(re.sub(r"!\s*important", "", color.group(1)).strip().lower())
            if declared and invisible_color(declared[0]):
                return False
        if prop == "outline-width":
            # Only an explicit zero length is zero. thin, medium, thick,
            # var(), and calc() are all visible widths, so the declaration
            # paints unless every token is a literal zero.
            return not (tokens and all(is_length(t) and ZERO_LENGTH.fullmatch(t) for t in tokens))
        if {"none", "hidden"} & set(tokens):
            return False
        if any(invisible_color(t) for t in tokens):
            return False
        if any(is_length(t) and ZERO_LENGTH.fullmatch(t) for t in tokens):
            return False
        return bool(tokens)
    if value in ("none", "") or prop != "box-shadow":
        return False
    for shadow in split_top_level(value):
        parts = css_tokens(shadow.strip())
        if any(invisible_color(t) for t in parts):
            continue
        # A var(), calc(), or other non-color function where a length goes
        # is an unknown, so possibly nonzero, length: 0 0 0 var(--ring) red
        # is a ring.
        unknown = [
            t for t in parts
            if re.fullmatch(r"[a-z-]+\(.*\)", t) and t.split("(", 1)[0] not in COLOR_FUNCTIONS
        ]
        lengths = [t for t in parts if is_length(t)]
        if not unknown and lengths and all(ZERO_LENGTH.fullmatch(t) for t in lengths):
            continue
        return True
    return False


def check_skip_link_and_focus_visibility():
    """A skip link nobody can see is a skip link nobody can use.

    Two halves of one problem. The skip link has to be the first focusable
    thing in the document, or a keyboard user tabs through the whole nav
    before reaching the control that exists to let them skip the nav. And
    the stylesheet suppressed the focus ring site-wide, so even once the
    link took focus there was nothing on screen to say so.

    :focus-visible rather than :focus on purpose. A mouse click on a link
    also focuses it, and an outline that appears on every click reads as a
    rendering bug, which is what led to outline: none in the first place.
    """
    print("\nThe skip link is first, and focus is visible")

    source = read_markup_or_fail(INDEX)
    css = read_or_fail(STYLE_CSS)
    if source is None or css is None:
        return
    css = without_comments(css, "css")

    body = re.search(r"<body[^>]*>(.*)</body>", source, re.S | re.I)
    if not check(body is not None, "index.html has a body"):
        return

    first = re.search(
        r"<(?:a\b[^>]*\bhref|button|input|select|textarea)\b[^>]*>",
        body.group(1),
        re.I,
    )
    if not check(first is not None, "index.html has a focusable element"):
        return
    check(
        "skip-link" in first.group(0),
        "the first focusable element is the skip link (found %s)"
        % " ".join(first.group(0).split())[:60],
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

    # Until issue 31 this asserted an `a:focus:not(:focus-visible) { outline:
    # none }` rule, which existed only to beat bootstrap.min.css's `a:focus {
    # outline: 5px auto }`: with the blanket suppression deleted, that rule
    # painted a ring on every mouse click. Bootstrap is gone, and the
    # browser's own stylesheet keys its ring on :focus-visible, so a click
    # paints none without any rule. What the old rule protected is asserted
    # instead: no stylesheet a page uses sets a visible outline on plain
    # :focus, which is the only way the click ring can come back. The skip
    # link is exempt; its :focus rule is deliberate and sets no outline.
    offenders = []
    for path in HTML_PAGES:
        page = read_markup(path)
        if page is None:
            continue
        facts = markup_facts(page)
        sheets = list(facts.styles)
        for href in facts.sheets:
            local = local_sheet(href)
            if local is not None:
                sheets.append(read(local))
        for sheet in sheets:
            sheet = without_comments(sheet, "css")
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
                for part in selector.split(","):
                    part = part.strip()
                    if ":focus" not in part or ":focus-visible" in part:
                        continue
                    if part.startswith(".skip-link"):
                        continue
                    # !important does not change what is painted, so it is
                    # stripped before comparing: `outline: none !important`
                    # paints nothing. A box-shadow is a ring too, and a plain
                    # :focus rule paints it on every mouse click.
                    for prop in ("outline", "outline-style", "outline-width", "box-shadow"):
                        declared = re.search(
                            r"(?<![-\w])%s\s*:\s*([^;}]+)" % prop, body
                        )
                        if declared is None:
                            continue
                        value = re.sub(r"!\s*important", "", declared.group(1)).strip().lower()
                        if paints_ring(prop, value, body):
                            offenders.append("%s: %s { %s }" % (path.name, part, prop))
    check(
        not offenders,
        "no stylesheet paints an outline or box-shadow on plain :focus, so a mouse click shows no ring%s"
        % (" (found %s)" % "; ".join(sorted(set(offenders))) if offenders else ""),
    )


# Bootstrap 3's grid, utilities, and collapse plugin markup. Issue 31 removed
# bootstrap.min.css and its JavaScript, so any of these left in the markup
# styles nothing and does nothing.
BOOTSTRAP_CLASS = re.compile(
    r"col-(?:xs|sm|md|lg)-\d+|col-(?:xs|sm|md|lg)-(?:offset|push|pull)-\d+|row|collapse"
    r"|text-(?:muted|left|right|justify|primary|success|info|warning|danger)"
    r"|navbar-(?:right|left|default|inverse|fixed-top|fixed-bottom|static-top|form|btn|text|link)"
    r"|pull-(?:left|right)|center-block|clearfix|img-(?:responsive|rounded|circle|thumbnail)"
    r"|btn|btn-[\w-]+|(?:hidden|visible)-[\w-]+|glyphicon|glyphicon-[\w-]+"
    r"|well|well-[\w-]+|panel|panel-[\w-]+|label-[\w-]+|badge|caret|dropdown|dropdown-[\w-]+"
    r"|list-(?:unstyled|inline)"
)

# Bootstrap class names a page already uses as its own, with the page that
# styles it. thanks.html and 404.html each declare .panel in their own inline
# <style> for their one content box; neither ever loaded Bootstrap. The
# exemption holds only while that rule exists.
SITE_OWNED_CLASSES = {
    "panel": ("thanks.html", "404.html"),
}

# Class names Bootstrap used to style that index.html still uses as the
# site's own. Each must now have a rule in css/style.css: an unstyled sr-only,
# for one, silently renders its label visible and pushes the form apart.
LOCAL_CLASSES = (
    "container", "sr-only", "text-center", "navbar-header", "navbar-collapse",
    "navbar-nav", "navbar-toggle", "navbar-brand", "icon-bar", "nav",
)


CONTINUES_AFTER = set("+-*/%?:&|=,(<>!^~")
CONTINUES_BEFORE = set("?:+-*/%&|.,=<>^")


def js_expression(code, start, stops=",)", statement=False):
    """(text, end) of the JavaScript expression starting at code[start].

    It ends at the first character in stops that sits outside every bracket
    and string, so el(String("span"), a ? "b" : "c") splits into its two
    arguments correctly. Strings, template literals, and nested calls are
    stepped over whole. Line breaks do not end it: a ternary or a
    concatenation broken across lines, as Prettier writes them, is one
    expression. With statement=True (the right side of an assignment), a
    line break ends it only where the statement ends without a semicolon:
    the line before does not end in an operator and the next does not start
    with one.
    """
    depth, index, length = 0, start, len(code)
    while index < length:
        char = code[index]
        if statement and char == "\n" and depth == 0:
            before = code[start:index].rstrip()
            after = code[index:].lstrip()
            if before and after and before[-1] not in CONTINUES_AFTER and after[0] not in CONTINUES_BEFORE:
                break
        if char in "\"'`":
            index = skip_js_string(code, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and char in stops:
            break
        index += 1
    return code[start:index], index


def skip_js_string(code, start):
    """Index just past the string or template literal opening at code[start]."""
    quote, index, length = code[start], start + 1, len(code)
    while index < length:
        char = code[index]
        if char == "\\":
            index += 2
            continue
        if quote == "`" and code.startswith("${", index):
            _, index = js_expression(code, index + 2, "}")
            index += 1
            continue
        if char == quote:
            return index + 1
        index += 1
    return length


def string_parts(expression):
    """Every static string piece in an expression.

    Each quoted literal whole, each template literal's static text, and the
    strings inside its ${} parts, so a ternary, a concatenation, or a
    template yields every class name it can produce.
    """
    parts, index, length, braces = [], 0, len(expression), 0
    while index < length:
        char = expression[index]
        if char == "{":
            braces += 1
        elif char == "}":
            braces = max(0, braces - 1)
        if char in "\"'":
            end = skip_js_string(expression, index)
            # An operand of a comparison is a value being tested, not a
            # class: tag === "dropdown", "badge" !== kind. So is an object
            # key, a literal followed by a colon inside braces.
            before = expression[:index].rstrip()
            after = expression[end:].lstrip()
            compared = re.search(r"[=!]==?$", before) or re.match(r"[=!]==?", after)
            keyed = braces > 0 and after.startswith(":")
            if not (compared or keyed):
                parts.append(expression[index + 1:end - 1])
            index = end
        elif char == "`":
            end = skip_js_string(expression, index)
            body = expression[index + 1:end - 1]
            static, inner = "", 0
            while inner < len(body):
                if body.startswith("${", inner):
                    nested, close = js_expression(body, inner + 2, "}")
                    parts.extend(string_parts(nested))
                    static += " "
                    inner = close + 1
                    continue
                static += body[inner]
                inner += 1
            parts.append(static)
            index = end
        else:
            index += 1
    return parts


def script_class_tokens(source):
    """Class tokens an inline script puts in the DOM, read where classes go.

    Only class-bearing positions, each read as a whole expression: the
    second argument of the renderer's el(tag, className, text), the right
    side of .className = or +=, every argument of classList.add, toggle, or
    replace (only the first argument of toggle, whose second is the force
    flag), the value argument of setAttribute("class", ...), and class
    attributes inside an HTML string. Every string piece of those
    expressions counts, so a ternary, a concatenation, or a template literal
    cannot carry a class past the scan, except the operands of a comparison
    and object keys, which are tested values rather than classes. Strings anywhere else are not read:
    every word of every string used to count, which made card prose such as
    "works well" read as Bootstrap's .well class.
    """
    tokens = []

    def add(expression):
        for part in string_parts(expression):
            tokens.extend(part.split())

    for body in inline_scripts(source):
        code = strip_js_comments(body)
        for match in re.finditer(r"\bel\s*\(", code):
            _, comma = js_expression(code, match.end())
            if comma < len(code) and code[comma] == ",":
                expression, _ = js_expression(code, comma + 1)
                add(expression)
        for match in re.finditer(r"\.className\s*\+?=(?!=)", code):
            expression, _ = js_expression(code, match.end(), ";,)", statement=True)
            add(expression)
        for match in re.finditer(r"\.classList\s*\.\s*(?:add|replace)\s*\(", code):
            expression, _ = js_expression(code, match.end(), ")")
            add(expression)
        # toggle's second argument is the force flag, not a class.
        for match in re.finditer(r"\.classList\s*\.\s*toggle\s*\(", code):
            expression, _ = js_expression(code, match.end())
            add(expression)
        for match in re.finditer(r"\.setAttribute\s*\(\s*([\"'])class\1\s*,", code):
            expression, _ = js_expression(code, match.end())
            add(expression)
        for value in string_parts(code):
            for attr in re.findall(r"class\s*=\s*\\?[\"']([^\"'\\]*)", value):
                tokens.extend(attr.split())
            for attr in re.findall(r"class\s*=\s*([\w-]+)", value):
                tokens.append(attr)
    return tokens


def check_no_bootstrap_classes():
    """No Bootstrap class is left behind, and the ones the site kept are its own.

    Swept over every page and over the string literals in each page's inline
    scripts, because the portfolio renderer builds its cards' class names
    there, out of the markup scan's reach.
    """
    print("\nNo Bootstrap class or attribute survives, and kept class names are styled")

    for path in HTML_PAGES:
        source = read_markup(path)
        if source is None:
            continue
        facts = markup_facts(source)
        tokens = script_class_tokens(source) + facts.classes
        owned = set()
        styles = "\n".join(facts.styles)
        for token, pages in SITE_OWNED_CLASSES.items():
            if path.name in pages and re.search(
                r"(?m)^\s*\.%s\s*\{" % re.escape(token), without_comments(styles, "css")
            ):
                owned.add(token)
        found = sorted(set(t for t in tokens if BOOTSTRAP_CLASS.fullmatch(t)) - owned)
        check(
            not found,
            "%s uses no Bootstrap grid, utility, or collapse class%s"
            % (path.name, " (found %s)" % ", ".join(found) if found else ""),
        )
        attributes = sorted(set(re.findall(r"\b(data-toggle|data-target)\s*=", source)))
        check(
            not attributes,
            "%s carries no Bootstrap data attribute%s"
            % (path.name, " (found %s)" % ", ".join(attributes) if attributes else ""),
        )

    source = read_markup(INDEX)
    css = read(STYLE_CSS)
    if source is None or css is None:
        return
    css = without_comments(css, "css")
    used = set(script_class_tokens(source)) | set(markup_facts(source).classes)
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    for name in LOCAL_CLASSES:
        if name not in used:
            continue
        # A rule that styles the element itself: some selector whose subject
        # (last compound) carries the class with no pseudo-class or
        # pseudo-element after it, and that declares something. .sr-only:hover
        # or .navbar-header::before do not style the element at rest.
        styled = False
        for selector, body in rules:
            if not re.search(r"[\w-]\s*:", body):
                continue
            for part in selector.split(","):
                subject = re.split(r"\s*[>+~]\s*|\s+", part.strip())[-1]
                if re.search(r"\.%s(?![\w-])" % re.escape(name), subject) and ":" not in subject:
                    styled = True
        check(styled, "index.html's .%s has a rule in css/style.css" % name)


def grouped_rule_body(css, first_selector):
    """The declaration block of the rule whose selector list starts here.

    rule_body anchors on a selector standing alone. The focus rules are
    written as grouped selectors, so `a:focus-visible,` opens a list that runs
    several lines before the brace. Both shapes are accepted: the selector
    followed straight by its brace, or followed by a comma and the rest of
    the list first.
    """
    match = re.search(
        r"(?m)^%s\s*(?:,[^{]*)?\{(.*?)\}" % re.escape(first_selector), css, re.S
    )
    return match.group(1) if match else None


def declared_hex(body, prop):
    """The first #rrggbb or #rgb in `prop`'s declaration, expanded.

    Handles the shorthand: `outline: 2px solid #232323` keeps its color at
    the end of the value, where declared_color's anchored pattern cannot see
    it.
    """
    match = re.search(r"(?<![-\w])%s\s*:([^;}]*)" % prop, body)
    if not match:
        return None
    found = re.search(OPAQUE_HEX, match.group(1))
    if not found:
        return None
    value = found.group(0)
    if len(value) == 4:
        value = "#" + "".join(char * 2 for char in value[1:])
    return value.lower()


def check_focus_ring_contrast():
    """A focus ring you cannot see against its own surface is not an indicator.

    WCAG 2.2 SC 1.4.11 puts non-text contrast at 3:1, and a focus indicator is
    the canonical example. Both entries below were real: the first draft of
    this stylesheet painted the ring white over the footer and over the nav,
    on the strength of a comment calling the footer dark. The footer is
    #f1f1f1, and .nav-sticky repaints the nav #fff as soon as the page scrolls
    past 100px, which is exactly when a visitor is most likely to be tabbing
    through it. Both rings were invisible.

    The hero is deliberately absent. Its surface is a photograph under a
    scrim, so there is no single background color to measure, and the white
    ring there is a judgment call rather than a computation.
    check_hero_text_contrast bounds the hero's text against the worst case,
    a white photo pixel, but a ring is not text and that bound is not applied
    to it here.
    """
    print("\nEvery focus ring contrasts with the surface it lands on")

    css = read_or_fail(STYLE_CSS)
    if css is None:
        return
    css = without_comments(css, "css")

    default = grouped_rule_body(css, "a:focus-visible")
    if not check(default is not None, "css/style.css declares a default focus ring"):
        return
    default_color = declared_hex(default, "outline")
    if not check(default_color is not None, "the default focus ring names a color"):
        return

    surfaces = [
        (default_color, "#ffffff", "the default ring on the page background"),
        (default_color, "#f1f1f1", "the default ring on the footer"),
    ]

    sticky = grouped_rule_body(css, ".nav-sticky a:focus-visible")
    if check(
        sticky is not None,
        "css/style.css gives the sticky nav its own focus ring color",
    ):
        sticky_color = declared_hex(sticky, "outline-color")
        if check(sticky_color is not None, "the sticky nav ring names a color"):
            surfaces.append((sticky_color, "#ffffff", "the sticky nav ring on its white bar"))

    for ring, surface, label in surfaces:
        ratio = contrast_ratio(ring, surface)
        check(
            ratio >= FOCUS_RING_MINIMUM,
            "%s is %.2f:1 (%s on %s), at or above %.1f:1"
            % (label, ratio, ring, surface, FOCUS_RING_MINIMUM),
        )


def check_site_root_files():
    """The three files a crawler and a mistyped URL look for.

    The important assertion is the Disallow one. A Disallow on a noindex page
    is the classic way to defeat your own noindex: the crawler is refused the
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
                node.text.strip() for node in root.iter(SITEMAP_NS + "loc") if node.text
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
                    "sitemap entry %s is a page that may be indexed" % page,
                )
            for page in sorted(INDEXABLE):
                expected = "https://%s/" % host
                if page != "index.html":
                    expected = "https://%s/%s" % (host, page)
                check(expected in locations, "sitemap lists %s" % expected)

    source = read_markup(NOT_FOUND)
    if check(source is not None, "404.html exists"):
        check(
            source.lstrip().lower().startswith("<!doctype html>"),
            "404.html opens with a doctype",
        )
        check(
            re.search(r'href="/"', source) is not None,
            "404.html links back to the site root",
        )


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
    match = re.search(r"(?m)^%s\s*\{(.*?)\}" % re.escape(selector), source, re.S)
    return match.group(1) if match else None


# Exactly three or six hex digits and nothing after them. A looser {3,6} read
# `#ffffff22` as an opaque `#ffffff`, dropping the alpha that makes it fail, and
# handed `#ffff` to relative_luminance, which crashed on it.
OPAQUE_HEX = r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"


def declared_color(body, prop):
    """A #rrggbb or #rgb value for `prop` in a declaration block, expanded.

    None for anything else, including a hex with an alpha channel, so a
    translucent color fails as unmeasured instead of passing as opaque.
    """
    match = re.search(r"(?<![-\w])%s\s*:\s*(%s)" % (prop, OPAQUE_HEX), body)
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
    and axe are for; both are run against the real page rather than the
    source.

    The foreground is read out of the file, which is the half that changes.
    The background is only named here when the rule does not declare its own,
    because it cannot be derived from the CSS alone: .portfolio-description p
    declares a color and inherits the white from .portfolio-card several
    levels up.

    AA is 4.5:1 for body text. Every pair below is body text: the largest is
    16px, well under the 18.66px bold or 24px regular that would qualify for
    the 3:1 large-text threshold.
    """
    print("\nCard text meets the AA contrast threshold")

    source = read_or_fail(STYLE_CSS)
    if source is None:
        return
    source = without_comments(source, "css")

    for selector, assumed_background in CONTRAST_PAIRS:
        body = rule_body(source, selector)
        if not check(body is not None, "css/style.css styles %s" % selector):
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


# The photo under the hero cannot be read from source, so the hero text is
# measured against the brightest pixel any photo can contain. That is the real
# worst case, not a theoretical one: the browser measurement for issue 34 found
# the subtitle crossing sun glints on the water at effectively pure white, at
# every viewport and in both the WebP and the JPEG.
HERO_WORST_PHOTO_PIXEL = "#ffffff"

# The hero subtitle is 22px, 26px from 768px up, at a computed weight of 700.
# Bold at 18.66px or more is large text under WCAG, so its bar is 3:1.
HERO_LARGE_TEXT_MINIMUM = 3.0

OG_CARD_SCRIPT = ROOT / "tools" / "make_og_card.py"

BLACK_RGBA = re.compile(
    r"^rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*([-+]?\d*\.?\d+)\s*\)$"
)


def style_rules(css, nested=()):
    """Every style rule as (selector list, declarations, nested), at any depth.

    A small brace walker, the same shape as verify_interactivity.css_rules: it
    descends into any at-rule block, so a rule inside a breakpoint is listed
    like any other. `nested` is the tuple of enclosing at-rule preludes, empty
    (and so false) for a top-level rule.

    A statement at-rule (`@import ...;`, `@charset ...;`, `@layer a, b;`) ends
    at its semicolon and has no block, so the text before a brace is cut at
    its last top-level semicolon. Without that, the statement and the rule
    after it read as one prelude starting with `@`, and that rule was lost.
    """
    rules = []
    index = 0
    while index < len(css):
        brace = css.find("{", index)
        if brace == -1:
            break
        prelude = split_top_level(css[index:brace], ";")[-1].strip()
        depth, end = 1, brace + 1
        while depth and end < len(css):
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        body = css[brace + 1:end - 1]
        if prelude.startswith("@"):
            rules.extend(style_rules(body, nested + (" ".join(prelude.split()),)))
        else:
            rules.append((prelude, body, nested))
        index = end
    return rules


def declaration(body, prop):
    """The raw value of `prop` in a declaration block, or None."""
    match = re.search(r"(?<![-\w])%s\s*:\s*([^;}]*)" % re.escape(prop), body)
    return match.group(1).strip() if match else None


def black_alpha(value):
    """A from `rgba(0, 0, 0, A)`, or None when the value is anything else."""
    if value is None:
        return None
    match = BLACK_RGBA.match(value.strip())
    return float(match.group(1)) if match else None


def over(top, alpha, bottom):
    """`top` at `alpha` composited over `bottom`, both #rrggbb, in sRGB.

    Per channel in 0-255 sRGB, which is how browsers layer background-color
    (non-linear blending), rounded and formatted so contrast_ratio reads it.
    """
    top = top.lstrip("#")
    bottom = bottom.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        upper = int(top[i:i + 2], 16)
        lower = int(bottom[i:i + 2], 16)
        channels.append(int(round(upper * alpha + lower * (1 - alpha))))
    return "#%02x%02x%02x" % tuple(channels)


def selector_list_has(selectors, wanted):
    """True when one comma-separated selector in the list is exactly `wanted`."""
    return any(
        re.sub(r"\s+", " ", part.strip()) == wanted for part in selectors.split(",")
    )


def check_hero_text_contrast():
    """Hero text clears its threshold against white under the scrim (issue 34).

    The subtitle and the photo credit sit on a photograph, which neither axe
    nor Lighthouse can measure and no source check can read. What source can
    bound is the worst case: the brightest pixel a photo can hold is white, and
    every layer between it and the text is declared here. So the check takes
    white, composites the .home-1:after scrim over it, then the credit's own
    backing for the credit, and holds each text color to its WCAG threshold
    against the result. Raising the scrim, changing a text color, or dropping
    the credit's backing all recheck automatically.

    Only flat black rgba layers can be proven this way. A gradient, image, or
    colored scrim fails the parse rather than passing silently, which forces
    this check to be rewritten alongside it.

    The credit link must also be underlined, so it is told apart from the
    credit text without relying on color (SC 1.4.1). And make_og_card.py's
    SCRIM must equal the CSS scrim, so the share card cannot drift from the
    hero again.
    """
    print("\nHero text contrasts with the brightest photo pixel under the scrim")

    css = read_or_fail(STYLE_CSS)
    if css is None:
        return
    css = without_comments(css, "css")
    rules = style_rules(css)

    scrim_body = rule_body(css, ".home-1:after")
    if not check(scrim_body is not None, "css/style.css styles .home-1:after"):
        return
    scrim = black_alpha(declaration(scrim_body, "background-color"))
    if not check(
        scrim is not None and 0 <= scrim <= 1,
        ".home-1:after paints a black rgba scrim with alpha in [0, 1]",
    ):
        return
    under_scrim = over("#000000", scrim, HERO_WORST_PHOTO_PIXEL)

    # Subtitle.
    subtitle = rule_body(css, "#home .typer-title")
    if check(subtitle is not None, "css/style.css styles #home .typer-title"):
        color = declared_color(subtitle, "color")
        if check(color is not None, "#home .typer-title declares a hex text color"):
            ratio = contrast_ratio(color, under_scrim)
            check(
                ratio >= HERO_LARGE_TEXT_MINIMUM,
                "%s is %.2f:1 (%s on %s, white photo pixel under the %.2f scrim), "
                "at or above %.1f:1"
                % ("the hero subtitle", ratio, color, under_scrim, scrim,
                   HERO_LARGE_TEXT_MINIMUM),
            )
    # Every rule naming .typer-title, at any @media depth, that sets a color.
    # The first top-level #home .typer-title rule is the one measured above
    # and the only one allowed, so neither a breakpoint override nor a later
    # rule can repaint the subtitle in a color this check never measured.
    overrides = []
    measured_seen = False
    for selectors, body, nested in rules:
        if ".typer-title" not in selectors or declaration(body, "color") is None:
            continue
        if not nested and not measured_seen and selectors == "#home .typer-title":
            measured_seen = True
            continue
        overrides.append(selectors)
    check(
        not overrides,
        "no other rule sets the subtitle's color%s"
        % ("" if not overrides else " (found: %s)" % "; ".join(overrides)),
    )

    # Credit.
    credit = rule_body(css, "#credit")
    credit_surface = None
    if check(credit is not None, "css/style.css styles #credit"):
        credit_color = declared_color(credit, "color")
        check(credit_color is not None, "#credit declares an opaque hex text color")
        backing = black_alpha(
            declaration(credit, "background")
            or declaration(credit, "background-color")
        )
        if check(
            backing is not None and 0 <= backing <= 1,
            "#credit declares a black rgba background behind the text",
        ):
            credit_surface = over("#000000", backing, under_scrim)
            if credit_color is not None:
                ratio = contrast_ratio(credit_color, credit_surface)
                check(
                    ratio >= CONTRAST_MINIMUM,
                    "%s is %.2f:1 (%s on %s, white photo pixel under the %.2f scrim "
                    "and the %.2f backing), at or above %.1f:1"
                    % ("the photo credit", ratio, credit_color, credit_surface,
                       scrim, backing, CONTRAST_MINIMUM),
                )

    # Credit link.
    link_rules = [
        body for selectors, body, _ in rules if selector_list_has(selectors, "#credit a")
    ]
    underlined = any(
        "underline" in (
            (declaration(body, "text-decoration") or "")
            + " "
            + (declaration(body, "text-decoration-line") or "")
        )
        for body in link_rules
    )
    check(underlined, "#credit a is underlined, so the link does not rely on color")
    for body in link_rules:
        if declaration(body, "color") is None:
            continue
        link_color = declared_color(body, "color")
        if not check(link_color is not None, "#credit a declares a hex text color"):
            continue
        if credit_surface is None:
            fail("#credit a has a known background to measure against")
            continue
        ratio = contrast_ratio(link_color, credit_surface)
        check(
            ratio >= CONTRAST_MINIMUM,
            "%s is %.2f:1 (%s on %s, white photo pixel under the %.2f scrim "
            "and the credit backing), at or above %.1f:1"
            % ("the photo credit link", ratio, link_color, credit_surface,
               scrim, CONTRAST_MINIMUM),
        )

    # Share card.
    script = read_or_fail(OG_CARD_SCRIPT)
    if script is None:
        return
    match = re.search(r"(?m)^SCRIM\s*=\s*([-+]?\d*\.?\d+)\s*$", script)
    if not check(match is not None, "tools/make_og_card.py declares SCRIM"):
        return
    card_scrim = float(match.group(1))
    check(
        abs(card_scrim - scrim) < 1e-9,
        "tools/make_og_card.py's SCRIM (%.2f) equals the hero scrim (%.2f)"
        % (card_scrim, scrim),
    )


# Elements HTMLParser never pushes onto its open-element stack, because they
# have no end tag.
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "source", "track", "wbr",
}

# Pseudo-classes that hold only in some states or positions. A selector using
# one is conditional: it can win when its state holds, but it never shadows
# anything, because the state may not hold.
STATE_PSEUDO_CLASSES = {
    "hover", "focus", "focus-visible", "focus-within", "active", "visited",
    "link", "any-link", "target", "checked", "first-child", "last-child",
    "only-child", "first-of-type", "last-of-type", "only-of-type", "empty",
    "nth-child", "nth-last-child", "nth-of-type", "nth-last-of-type", "not",
    "is", "where", "has", "lang", "dir", "root",
}

# Pseudo-elements that paint the element's own text, so a rule on them is a
# rule on the text. ::after is the scrim's and is handled on its own.
TEXT_PSEUDO_ELEMENTS = {"first-line", "first-letter"}
LEGACY_PSEUDO_ELEMENTS = {"after", "before", "first-line", "first-letter"}

# Properties grouped by what they set. Two declarations in one group compete,
# so `background` after `background-color` in the same rule replaces it.
PROPERTY_GROUPS = {
    "color": "color",
    "-webkit-text-fill-color": "text-fill",
    "background": "background",
    "background-color": "background",
    "opacity": "opacity",
    "font-weight": "font-weight",
    "font-size": "font-size",
    "font": "font",
    "text-decoration": "text-decoration",
    "text-decoration-line": "text-decoration",
    "content": "content",
    "display": "display",
}

# WCAG large text: 18.66px (14pt) or more at bold. The subtitle's 3:1 bar
# depends on both.
LARGE_TEXT_BOLD_PX = 18.66
LARGE_TEXT_WEIGHT = 700


class HeroChains(HTMLParser):
    """The open-element stack, root first, at each hero target in index.html.

    Each entry is (tag, id, classes). The targets are the first #home section,
    the first .typer-title inside it, #credit, the first p in #credit, and the
    first a in that p.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.chains = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        entry = (tag, attrs.get("id") or "", set((attrs.get("class") or "").split()))
        if tag in VOID_ELEMENTS:
            return
        self.stack.append(entry)
        chain = list(self.stack)
        ids = [element[1] for element in chain]
        if entry[1] == "home" and tag == "section":
            self.chains.setdefault("section", chain)
        if "home" in ids and "typer-title" in entry[2]:
            self.chains.setdefault("subtitle", chain)
        if entry[1] == "credit":
            self.chains.setdefault("credit", chain)
        if "credit" in ids[:-1] and tag == "p":
            self.chains.setdefault("credit p", chain)
        if "credit" in ids[:-1] and tag == "a" and chain[-2][0] == "p":
            self.chains.setdefault("credit link", chain)

    def handle_endtag(self, tag):
        for position in range(len(self.stack) - 1, -1, -1):
            if self.stack[position][0] == tag:
                del self.stack[position:]
                return


def parse_compound(compound):
    """(tag, ids, classes, pseudo-classes, pseudo-element) of one compound.

    Functional pseudo-classes keep only their name: `:not(.x)` is read as
    `not`, which counts as conditional and matches anything. Attribute
    selectors are kept as a count and assumed to match.
    """
    tag = None
    ids, classes, pseudos, attrs = [], [], [], 0
    element = None
    pattern = re.compile(
        r"(::?)([\w-]+)(\((?:[^()]|\([^()]*\))*\))?"  # pseudo, with any argument
        r"|#([\w-]+)|\.([\w-]+)|(\[[^\]]*\])|(\*|[a-zA-Z][\w-]*)"
    )
    for match in pattern.finditer(compound):
        colons, name, _, id_, class_, attr, type_ = match.groups()
        if name:
            name = name.lower()
            if colons == "::" or name in LEGACY_PSEUDO_ELEMENTS:
                element = name
            else:
                pseudos.append(name)
        elif id_:
            ids.append(id_)
        elif class_:
            classes.append(class_)
        elif attr:
            attrs += 1
        elif type_:
            tag = type_.lower()
    return tag, ids, classes, pseudos, element, attrs


def split_complex(selector):
    """A complex selector as [compound, combinator, compound, ...]."""
    flat = re.sub(r"\((?:[^()]|\([^()]*\))*\)", lambda m: m.group(0).replace(" ", ""), selector)
    flat = re.sub(r"\s*([>+~])\s*", r"\1", " ".join(flat.split()))
    return [part for part in re.split(r"([>+~ ])", flat) if part]


def specificity(selector):
    """(ids, classes, types) of one complex selector, approximately."""
    ids = classes = types = 0
    for part in split_complex(selector):
        if part in (">", "+", "~", " "):
            continue
        tag, id_list, class_list, pseudos, element, attrs = parse_compound(part)
        ids += len(id_list)
        classes += len(class_list) + attrs + len([p for p in pseudos if p != "where"])
        types += (1 if tag and tag != "*" else 0) + (1 if element else 0)
    return ids, classes, types


def compound_matches(parsed, element):
    tag, ids, classes, _, _, _ = parsed
    if tag and tag != "*" and tag != element[0]:
        return False
    if any(id_ != element[1] for id_ in ids):
        return False
    return set(classes) <= element[2]


def selector_targets(selector, chain, pseudo_element=None):
    """Whether `selector` can match chain[-1] (or its `pseudo_element`).

    Not a selector engine. Descendant and child combinators are followed
    against the real ancestor chain from index.html; a sibling combinator is
    assumed to find its sibling. Pseudo-classes are assumed to hold.
    """
    parts = split_complex(selector)
    if not parts:
        return False
    compounds = parts[0::2]
    combinators = parts[1::2]
    last = parse_compound(compounds[-1])
    if not any(last[:5]) and not last[5]:
        return False  # nothing element-shaped, such as a keyframe's `40%`
    if pseudo_element is None:
        if last[4] is not None and last[4] not in TEXT_PSEUDO_ELEMENTS:
            return False
    elif last[4] != pseudo_element:
        return False
    if not compound_matches(last, chain[-1]):
        return False

    def walk(index, position):
        # compounds[index] matched chain[position]; match what precedes it.
        if index == 0:
            return True
        combinator = combinators[index - 1]
        parsed = parse_compound(compounds[index - 1])
        if combinator in ("+", "~"):
            # The sibling is not in the chain; it shares chain[position]'s
            # parent, so carry on from the same position.
            return walk(index - 1, position)
        if combinator == ">":
            return (
                position > 0
                and compound_matches(parsed, chain[position - 1])
                and walk(index - 1, position - 1)
            )
        return any(
            compound_matches(parsed, chain[ancestor]) and walk(index - 1, ancestor)
            for ancestor in range(position - 1, -1, -1)
        )

    return walk(len(compounds) - 1, len(chain) - 1)


def declarations(body):
    """[(property, value, important)] in source order."""
    out = []
    for part in split_top_level(body, ";"):
        if ":" not in part:
            continue
        prop, value = part.split(":", 1)
        prop = prop.strip().lower()
        value = " ".join(value.split())
        important = bool(re.search(r"!\s*important\s*$", value, re.I))
        value = re.sub(r"\s*!\s*important\s*$", "", value, flags=re.I)
        out.append((prop, value, important))
    return out


def hero_declarations(rules, chain, pseudo_element=None):
    """Every declaration that can apply to the chain's last element, by group.

    Returns {group: [(precedence, conditional, value, where, prop)]} plus a
    list of (group, message) for rules that declare one group twice.
    """
    found = {}
    doubled = []
    for order, (selectors, body, nested) in enumerate(rules):
        # A keyframe's selector is a percentage, not an element selector.
        if any(re.match(r"@(?:-[\w]+-)?keyframes\b", prelude) for prelude in nested):
            continue
        for selector in split_top_level(selectors, ","):
            selector = " ".join(selector.split())
            if not selector or not selector_targets(selector, chain, pseudo_element):
                continue
            where = selector + ("" if not nested else " (in %s)" % " ".join(nested))
            pseudos = [
                name
                for part in split_complex(selector)
                if part not in (">", "+", "~", " ")
                for name in parse_compound(part)[3]
            ]
            conditional = bool(nested) or any(name in STATE_PSEUDO_CLASSES for name in pseudos)
            seen = {}
            for prop, value, important in declarations(body):
                group = PROPERTY_GROUPS.get(prop)
                if group is None:
                    continue
                if group in seen:
                    doubled.append(
                        (group, "%s declares %s and %s in one rule" % (where, seen[group], prop))
                    )
                seen[group] = prop
                precedence = (important, specificity(selector), order)
                found.setdefault(group, []).append((precedence, conditional, value, where, prop))
    return found, doubled


def can_win(entries):
    """(entries that can win in some state, the unconditional winner or None).

    An entry can win unless an unconditional entry outranks it. Conditional
    entries never shadow anything, because their condition may not hold.
    """
    unconditional = [entry for entry in entries if not entry[1]]
    winner = max(unconditional, key=lambda entry: entry[0]) if unconditional else None
    live = [
        entry for entry in entries
        if winner is None or entry is winner or entry[0] > winner[0]
    ]
    return live, winner


def hex_value(value):
    match = re.fullmatch(OPAQUE_HEX, value.strip())
    if not match:
        return None
    value = match.group(0)
    if len(value) == 4:
        value = "#" + "".join(char * 2 for char in value[1:])
    return value.lower()


def px_value(value):
    match = re.fullmatch(r"([\d.]+)px", value.strip().lower())
    return float(match.group(1)) if match else None


def weight_value(value):
    value = value.strip().lower()
    if value in ("bold", "bolder"):
        return 700
    if value in ("normal", "lighter"):
        return 400
    return int(value) if re.fullmatch(r"\d{3,4}", value) else None


def check_hero_text_cannot_be_overridden():
    """No rule in css/style.css can change what check_hero_text_contrast read.

    That check reads one rule per target and trusts it. Review of issue 34
    found nine ways the rendered hero could differ while it passed: an
    `::after` or @media scrim, a later duplicate declaration, a breakpoint or
    `#credit p` color, a link color from `.home-1 a` or the global `a` rule,
    a hover rule removing the underline, a more specific selector that never
    names .typer-title, and opacity, -webkit-text-fill-color, or a smaller
    or lighter subtitle that loses the large-text bar. This closes them.

    For each hero target (the scrim pseudo-element, the subtitle, the credit,
    its paragraph, and its link) it takes the element's real ancestor chain
    from index.html, finds every rule in css/style.css at any at-rule depth
    whose selector can match it, and orders their declarations by !important,
    specificity, and source order. A declaration can win unless an
    unconditional one outranks it; one inside any at-rule (@media, @supports)
    or behind a state or structural pseudo-class such as :hover is
    conditional, so it may win but never shadows. Rules inside @keyframes are
    not element rules and are skipped. Every declaration that can win must be
    compatible: black rgba scrims and backings no lighter than the lightest
    measured, an unconditional content on the scrim, text colors measured
    against the worst surface at the target's threshold, a subtitle at weight
    700 or more and 18.66px or more in px, an underline on every link rule,
    no layer between the section and the text other than black rgba,
    transparent, or none, and no opacity or text fill anywhere on the chain.
    A rule declaring one property group twice on a target element fails
    outright, for the groups that target is measured on; the same on an
    ancestor is an ordinary fallback and passes.

    This is a heuristic matcher, not a cascade resolver. Its limits:

    - It reads css/style.css only. Inline style attributes and <style>
      blocks in index.html are not read.
    - It checks the target elements and their ancestors, not descendants. An
      element inside the subtitle or the link with its own color is
      unchecked.
    - It follows descendant and child combinators against the real
      ancestors and assumes a sibling combinator and every pseudo-class can
      match.
    - ::first-line and ::first-letter rules are ranked by specificity like
      any other, although in a browser they win over the element's own
      rules outright.
    - It reads only the properties above. `all`, `filter`,
      `mix-blend-mode`, and CSS custom properties are not examined.
    """
    print("\nNo other rule can change the hero text's measured contrast")

    css = read_or_fail(STYLE_CSS)
    markup = read_or_fail(INDEX)
    if css is None or markup is None:
        return
    rules = style_rules(without_comments(css, "css"))
    parser = HeroChains()
    parser.feed(without_comments(markup, "html"))
    chains = parser.chains
    for name in ("section", "subtitle", "credit", "credit p", "credit link"):
        check(name in chains, "index.html has the hero %s" % name)
    if len(chains) < 5:
        return

    problems = []

    # The property groups each target is measured on. A rule declaring one of
    # these twice on a target fails; a duplicate on an ancestor, or in a group
    # the target is not measured on, is an ordinary fallback and is left alone.
    measured = {
        "scrim": {"background", "content", "display", "opacity", "text-fill"},
        "subtitle": {
            "color", "background", "font-weight", "font-size", "font", "opacity", "text-fill",
        },
        "credit": {"color", "background", "opacity", "text-fill"},
        "credit p": {"color", "background", "opacity", "text-fill"},
        "credit link": {"color", "background", "text-decoration", "opacity", "text-fill"},
    }

    def collect(chain, pseudo_element=None, target=None):
        found, doubled = hero_declarations(rules, chain, pseudo_element)
        if target is not None:
            problems.extend(
                message for group, message in doubled if group in measured[target]
            )
        return {group: can_win(entries) for group, entries in found.items()}

    def black_layer(group_state, label, required):
        """(minimum alpha over every live black-rgba layer, its rule), or Nones.

        `required` is for the scrim and the credit's backing, which must be
        black rgba. Any other layer only has to be no lighter than nothing,
        so `transparent` and `none` pass there.
        """
        live, winner = group_state.get("background", ([], None))
        if required and winner is None:
            problems.append("%s has no unconditional background" % label)
        alphas = []
        for _, _, value, where, prop in live:
            if not required and value.strip().lower() in ("transparent", "none"):
                continue
            alpha = black_alpha(value)
            if alpha is None or not 0 <= alpha <= 1:
                problems.append(
                    "%s sets %s: %s on %s, which is not a black rgba layer"
                    % (where, prop, value, label)
                )
            else:
                alphas.append((alpha, where))
        return min(alphas) if alphas else (None, None)

    def no_fade(chain_label, chain, pseudo_element=None):
        for depth in range(1, len(chain) + 1):
            state = collect(chain[:depth], pseudo_element if depth == len(chain) else None)
            for _, _, value, where, prop in state.get("opacity", ([], None))[0]:
                if value.strip() not in ("1", "1.0", "100%"):
                    problems.append(
                        "%s sets opacity: %s over the %s" % (where, value, chain_label)
                    )
            for _, _, value, where, prop in state.get("text-fill", ([], None))[0]:
                if value.strip().lower() != "currentcolor":
                    problems.append(
                        "%s sets -webkit-text-fill-color: %s over the %s"
                        % (where, value, chain_label)
                    )

    # The scrim.
    scrim_state = collect(chains["section"], "after", "scrim")
    scrim, scrim_rule = black_layer(scrim_state, "the hero scrim", True)
    # A pseudo-element with no content is never generated, so the scrim is
    # only drawn when an unconditional rule gives it one.
    content_winner = scrim_state.get("content", ([], None))[1]
    if content_winner is None or content_winner[2].strip().lower() in ("none", "normal"):
        problems.append(
            "the hero scrim has no unconditional content declaration, so it is never drawn"
        )
    for group in ("content", "display"):
        for _, _, value, where, prop in scrim_state.get(group, ([], None))[0]:
            if value.strip().lower() in ("none", "normal"):
                problems.append("%s sets %s: %s, removing the hero scrim" % (where, prop, value))
    no_fade("hero scrim", chains["section"], "after")
    if scrim is None:
        for message in problems:
            fail(message)
        check(False, "the hero scrim resolves to a black rgba layer")
        return
    under_scrim = over("#000000", scrim, HERO_WORST_PHOTO_PIXEL)
    scrim_layer = "the %.2f scrim from %s" % (scrim, scrim_rule)

    def no_light_layers(chain, label):
        # Between the section and the text, any background must be black rgba.
        for depth in range(len(chains["section"]) + 1, len(chain) + 1):
            black_layer(collect(chain[:depth]), label, False)

    def colors(state, label, surface, minimum, inherits, layers):
        live, winner = state.get("color", ([], None))
        if not inherits and winner is None:
            problems.append("%s has no unconditional color of its own" % label)
        for _, _, value, where, prop in live:
            if inherits and value.strip().lower() in ("inherit", "currentcolor"):
                continue
            color = hex_value(value)
            if color is None:
                problems.append(
                    "%s sets color: %s on the %s, not an opaque hex" % (where, value, label)
                )
                continue
            ratio = contrast_ratio(color, surface)
            if ratio < minimum:
                problems.append(
                    "%s sets color: %s on the %s, %.2f:1 on %s (white under %s), under %.1f:1"
                    % (where, value, label, ratio, surface, layers, minimum)
                )

    # The subtitle.
    subtitle_chain = chains["subtitle"]
    subtitle = collect(subtitle_chain, target="subtitle")
    colors(subtitle, "hero subtitle", under_scrim, HERO_LARGE_TEXT_MINIMUM, False, scrim_layer)
    no_light_layers(subtitle_chain, "the hero subtitle")
    no_fade("hero subtitle", subtitle_chain)
    for _, _, value, where, prop in subtitle.get("font", ([], None))[0]:
        problems.append(
            "%s sets the font shorthand on the hero subtitle, which this check "
            "does not read" % where
        )
    live, winner = subtitle.get("font-weight", ([], None))
    if winner is None:
        problems.append("the hero subtitle has no unconditional font-weight of its own")
    for _, _, value, where, prop in live:
        weight = weight_value(value)
        if weight is None or weight < LARGE_TEXT_WEIGHT:
            problems.append(
                "%s sets font-weight: %s on the hero subtitle, under the %d its 3:1 bar needs"
                % (where, value, LARGE_TEXT_WEIGHT)
            )
    live, winner = subtitle.get("font-size", ([], None))
    if winner is None:
        problems.append("the hero subtitle has no unconditional font-size of its own")
    for _, _, value, where, prop in live:
        size = px_value(value)
        if size is None:
            problems.append(
                "%s sets font-size: %s on the hero subtitle, which is not a px value this "
                "check can read; use px or extend the check" % (where, value)
            )
        elif size < LARGE_TEXT_BOLD_PX:
            problems.append(
                "%s sets font-size: %s on the hero subtitle, under the %.2fpx its 3:1 bar needs"
                % (where, value, LARGE_TEXT_BOLD_PX)
            )

    # The credit, its paragraph, and its link.
    credit = collect(chains["credit"], target="credit")
    backing, backing_rule = black_layer(credit, "the photo credit", True)
    credit_surface = over("#000000", backing or 0, under_scrim)
    credit_layers = scrim_layer + (
        "" if backing is None else " and the %.2f backing from %s" % (backing, backing_rule)
    )
    colors(credit, "photo credit", credit_surface, CONTRAST_MINIMUM, False, credit_layers)
    for key, label in (
        ("credit p", "photo credit paragraph"),
        ("credit link", "photo credit link"),
    ):
        state = collect(chains[key], target=key)
        colors(state, label, credit_surface, CONTRAST_MINIMUM, True, credit_layers)
    no_light_layers(chains["credit link"], "the photo credit")
    no_fade("photo credit", chains["credit link"])
    link = collect(chains["credit link"])
    live, winner = link.get("text-decoration", ([], None))
    if winner is None or "underline" not in winner[2]:
        problems.append("the photo credit link is not underlined by an unconditional rule")
    for _, _, value, where, prop in live:
        if "underline" not in value:
            problems.append(
                "%s sets %s: %s on the photo credit link, dropping the underline"
                % (where, prop, value)
            )

    for message in dict.fromkeys(problems):
        fail(message)
    check(
        not problems,
        "every rule that can reach the scrim, subtitle, credit, or credit link agrees "
        "with what was measured (scrim %.2f, %d rules read)" % (scrim, len(rules)),
    )


def check_share_card_mirrors_hero_colors():
    """make_og_card.py draws the hero's headline and subtitle in the hero's colors.

    check_hero_text_contrast pins the card's scrim to the CSS. This pins the
    two text fills to the colors #home h1 and #home .typer-title declare, so
    a color change on the page cannot leave the card behind.
    """
    print("\nThe share card draws the hero text in the hero's colors")

    css = read_or_fail(STYLE_CSS)
    script = read_or_fail(OG_CARD_SCRIPT)
    if css is None or script is None:
        return
    css = without_comments(css, "css")
    for selector, font in (("#home h1", "name_font"), ("#home .typer-title", "role_font")):
        body = rule_body(css, selector)
        color = declared_color(body, "color") if body else None
        if not check(color is not None, "%s declares a hex text color" % selector):
            continue
        match = re.search(
            r"%s\s*,\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)" % font, script
        )
        if not check(match is not None, "tools/make_og_card.py draws a line in %s" % font):
            continue
        fill = "#%02x%02x%02x" % tuple(int(value) for value in match.groups())
        check(
            fill == color,
            "tools/make_og_card.py's %s fill %s equals %s's %s" % (font, fill, selector, color),
        )


def main():
    check_every_page_is_a_complete_document()
    check_every_page_has_a_description()
    check_every_page_declares_a_canonical()
    check_indexing_policy_is_explicit()
    check_share_card_exists_and_fits()
    check_homepage_carries_share_tags()
    check_homepage_has_person_structured_data()
    check_images_have_alt_text()
    check_interactive_elements_have_names()
    check_renderer_icons_are_hidden()
    check_new_tab_links_carry_rel()
    check_form_controls_are_labelled()
    check_skip_link_and_focus_visibility()
    check_no_bootstrap_classes()
    check_focus_ring_contrast()
    check_site_root_files()
    check_text_contrast()
    check_hero_text_contrast()
    check_hero_text_cannot_be_overridden()
    check_share_card_mirrors_hero_colors()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
