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
        if tag == "i" and "fa" in (attrs.get("class") or "").split():
            if (attrs.get("aria-hidden") or "").lower() != "true":
                self.problems.append(
                    'line %d: decorative <i class="fa ..."> is not aria-hidden'
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
                    "line %d: <%s> has no accessible name"
                    % (frame["line"], frame["tag"])
                )
            if frame["tag"] == tag:
                break


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
        source = read(path)
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

    source = read_or_fail(INDEX)
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

    source = read_or_fail(INDEX)
    css = read_or_fail(STYLE_CSS)
    if source is None or css is None:
        return

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
    check_new_tab_links_carry_rel()
    check_form_controls_are_labelled()
    check_skip_link_and_focus_visibility()
    check_site_root_files()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
