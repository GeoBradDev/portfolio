#!/usr/bin/env python3
"""Check the content and navigation criteria from issue 18.

Run from the repository root:

    python3 tools/verify_content.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.

Two of the issue's seven acceptance criteria were declined by the site owner
on 2026-08-12 and are deliberately not checked here:

  - "resume.html linked from the main nav". The resume is sent on request
    rather than published, so resume.html stays reachable by URL and unlinked.
  - "privacy.html linked from the footer". That policy belongs to a different
    project and is hosted here only so its existing URL keeps resolving.

Neither page is exempt from anything by being unlinked: verify_security.py
discovers pages with a glob over *.html at the repo root and sweeps both.
"""

import re
import sys
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RESUME = ROOT / "resume.html"
THANKS = ROOT / "thanks.html"
STYLE_CSS = ROOT / "css" / "style.css"
MAIN_JS = ROOT / "js" / "main.js"
CNAME = ROOT / "CNAME"

# Every page at the repo root, discovered from the filesystem rather than
# hardcoded, so a page added later is covered instead of silently exempt.
# Same rule verify_security.py uses, and for the same reason.
HTML_PAGES = sorted(ROOT.glob("*.html"))

# Left over from the ThemeForest template. verify_assets.DEAD_ASSETS covers
# the eight libraries and image originals that issue 15 removed; these two are
# what issue 18 found still in the tree afterwards.
LEFTOVER_TEMPLATE_FILES = [
    # A PHP mail handler on GitHub Pages, which cannot execute PHP, for a form
    # that posts to FormSubmit instead.
    "mail/contact.php",
    # 330 KB referenced from no page, no stylesheet, and no script.
    "video/video.mp4",
]

# Families that a bundled stylesheet defines rather than the page itself, as
# lowercased family name -> the href substring that proves it is linked. A
# page may name one of these without carrying its own @font-face.
FONT_FAMILIES_FROM = {
    "fontawesome": "css/font-awesome.min.css",
}

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
    leave this script asserting the old one.
    """
    text = read(CNAME)
    return text.strip() if text else None


def contact_form(source):
    """The <form id="contact-form"> block, or None."""
    match = re.search(r'<form[^>]*id="contact-form".*?</form>', source, re.S)
    return match.group(0) if match else None


def hidden_value(form, name):
    """The value attribute of the input named `name`, or None."""
    tag = re.search(r'<input[^>]*name="%s"[^>]*>' % re.escape(name), form)
    if tag is None:
        return None
    value = re.search(r'value="([^"]*)"', tag.group(0))
    return value.group(1) if value else None


def check_contact_form_returns_visitor():
    """FormSubmit strands the visitor on its own domain without _next.

    Without a _next field the visitor lands on a confirmation page at
    formsubmit.co and has no way back to the site. The value has to be
    absolute for FormSubmit to honor it, so this also asserts that it is
    https, that it stays on this site's own host, and that the page it names
    actually exists in the repo. A _next pointing at a 404 is worse than no
    _next at all.
    """
    print("\nThe contact form returns the visitor to the site")

    source = read_or_fail(INDEX)
    if source is None:
        return

    form = contact_form(source)
    if not check(form is not None, "index.html has a contact form"):
        return

    check(
        "formsubmit.co" in form,
        "the contact form still posts to FormSubmit",
    )

    next_url = hidden_value(form, "_next")
    if not check(next_url is not None, "the contact form carries a _next redirect"):
        return

    parsed = urllib.parse.urlparse(next_url)
    check(parsed.scheme == "https", "_next is an https URL (%s)" % next_url)

    host = site_host()
    if check(host is not None, "CNAME names the site host"):
        if parsed.netloc == host:
            print("  PASS  _next points at the host CNAME names (%s)" % host)
        else:
            fail(
                "_next points at %s, but CNAME names %s"
                % (parsed.netloc or "a relative path", host)
            )

    target = ROOT / parsed.path.lstrip("/")
    check(
        target.is_file(),
        "_next points at a page that exists in the repo (%s)" % parsed.path,
    )

    check(
        hidden_value(form, "_subject") is not None,
        "the contact form sets a _subject so the mail is identifiable",
    )


def check_thanks_page_is_a_complete_document():
    """The landing page for _next has to stand on its own.

    It is the first page some visitors see rendered, arriving from a third
    party domain with no referrer context, so it needs the head that
    index.html has: a doctype so it is not in quirks mode, a charset, a
    viewport so it is readable on a phone, a title for the tab, and a way
    back to the site.
    """
    print("\nthanks.html is a complete document")

    source = read_or_fail(THANKS)
    if source is None:
        return

    check(
        source.lstrip().lower().startswith("<!doctype html>"),
        "thanks.html opens with a doctype, so it renders in standards mode",
    )
    check("<html lang=" in source, "thanks.html declares a language")
    check(
        re.search(r"<meta[^>]+charset", source, re.I) is not None,
        "thanks.html declares a charset",
    )
    check(
        re.search(r'<meta[^>]+name="viewport"', source, re.I) is not None,
        "thanks.html declares a viewport, so it is readable on a phone",
    )
    title = re.search(r"<title>(.*?)</title>", source, re.S)
    check(
        title is not None and title.group(1).strip() != "",
        "thanks.html has a non-empty title",
    )
    check(
        re.search(r'href="/"', source) is not None,
        "thanks.html links back to the site root",
    )


def check_no_dead_form_error_markup():
    """Nothing writes to these elements, and nothing has since issue 16.

    The validation block in js/main.js that populated them was deleted, so
    the spans, the message div, and their CSS are markup and bytes that no
    code path can ever reach. This is the same rule issues 15 and 16 applied
    to dead libraries and dead JavaScript, held over the markup.
    """
    print("\nNo dead contact form validation markup")

    source = read_or_fail(INDEX)
    if source is not None:
        markup = without_comments(source, "html")
        for token in ("form-message", "name-error", "email-error", "message-error"):
            check(
                token not in markup,
                "index.html no longer carries the dead %s element" % token,
            )

    css = read_or_fail(STYLE_CSS)
    if css is not None:
        css = without_comments(css, "css")
        for token in ("name-error", "email-error", "message-error", "#form-message"):
            check(
                token not in css,
                "css/style.css no longer styles %s" % token,
            )
        # .error and .success are short enough to appear inside an unrelated
        # selector or a comment, so match them as a rule opening at the start
        # of a line rather than anywhere in the file.
        for selector in (".error", ".success"):
            check(
                re.search(r"(?m)^%s\s*\{" % re.escape(selector), css) is None,
                "css/style.css no longer opens a %s rule" % selector,
            )


def without_comments(source, style):
    """Strip comments so a scan reads code, not prose about code.

    These checks assert that a selector is no longer styled and that an
    element is no longer in the markup. A comment explaining why something
    was removed has to name the thing it removed, and a bare substring scan
    counts that explanation as the offense it is documenting. Strip comments
    first so the file can keep the explanation.
    """
    pattern = r"/\*.*?\*/" if style == "css" else r"<!--.*?-->"
    return re.sub(pattern, "", source, flags=re.S)


def declarations(css, selector):
    """The declaration body of the rule opening exactly at `selector`.

    Matches the selector at the start of a line so that .submit-btn does not
    also pull in .submit-btn:hover, and returns "" when the rule is absent.
    """
    rule = re.search(
        r"(?m)^%s\s*\{(.*?)\}" % re.escape(selector), css, re.S
    )
    return rule.group(1) if rule else ""


def check_contact_form_spacing_is_declared():
    """The deleted error spans were load-bearing, so the spacing must be real.

    Nothing wrote to them, but they were not weightless. Each empty span was
    display:block with margin-top:8px plus .mb-30's margin-bottom:30px, and
    #form-message was a full-width float with the same margin box, all inside
    floated grid columns where those margins could not collapse away. Removing
    them collapsed the gap between the name/email row and the textarea from
    30px to 0, and between the textarea and the button from 76px to 8px,
    measured in Chrome at 1280px against origin/main.

    So the spacing now has to be declared. Three declarations carry it, and
    this asserts each one exists rather than asserting a pixel value, which
    keeps the check source-level: what it prevents is a future edit dropping
    one and silently collapsing the form again.

    A margin-top on .submit-btn would not work and is deliberately not what
    is asserted. Every field sits in a floated grid column, so the button's
    static position is the top of the form, and clear: both turns any
    margin-top into clearance that absorbs it. The last float's bottom margin
    is what the button actually clears past, which is why the pre-button gap
    lives on textarea.input-field.
    """
    print("\nContact form spacing is declared, not emergent")

    css = read_or_fail(STYLE_CSS)
    if css is None:
        return

    margin_bottom = re.compile(r"(?<!-)margin-bottom\s*:")
    check(
        margin_bottom.search(declarations(css, ".input-field")) is not None,
        ".input-field declares the margin-bottom that spaces the fields",
    )
    check(
        margin_bottom.search(declarations(css, "textarea.input-field")) is not None,
        "textarea.input-field declares the margin-bottom that spaces the button",
    )
    check(
        re.search(r"(?<!-)clear\s*:", declarations(css, ".submit-btn")) is not None,
        ".submit-btn declares clear, so it lands below the floated columns",
    )


class ListMarkup(HTMLParser):
    """Find an <li> that opens while a sibling <li> is still open.

    HTMLParser reports raw tags and never auto-closes, which is exactly what
    is wanted here: browsers do the auto-closing that hides this bug. Each
    <ul>/<ol> pushes a context so a legitimately nested list is not misread
    as an unclosed item.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.lists = []

    def handle_starttag(self, tag, attrs):
        if tag in ("ul", "ol"):
            self.lists.append(False)
        elif tag == "li":
            if not self.lists:
                self.problems.append(
                    "line %d: <li> outside any list" % self.getpos()[0]
                )
                return
            if self.lists[-1]:
                self.problems.append(
                    "line %d: <li> opens while the previous <li> is still open"
                    % self.getpos()[0]
                )
            self.lists[-1] = True

    def handle_endtag(self, tag):
        if tag == "li":
            if self.lists:
                self.lists[-1] = False
        elif tag in ("ul", "ol"):
            if self.lists:
                if self.lists[-1]:
                    self.problems.append(
                        "line %d: </%s> closes with an <li> still open"
                        % (self.getpos()[0], tag)
                    )
                self.lists.pop()


def check_list_markup_is_balanced():
    """Every page, not just index.html.

    The bug this guards is an <li> a browser silently auto-closes, and any
    page with a list can carry it. resume.html has lists; scanning only the
    page the bug happened to be found on would let the next one ship green.
    """
    print("\nEvery list item is closed")

    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        name = path.relative_to(ROOT)

        parser = ListMarkup()
        parser.feed(source)
        if parser.problems:
            for problem in parser.problems:
                fail("%s %s" % (name, problem))
        else:
            print("  PASS  %s closes every <li>" % name)


def check_leftover_template_files_are_gone():
    print("\nLeftover template files are gone")

    for name in LEFTOVER_TEMPLATE_FILES:
        check(not (ROOT / name).exists(), "%s is gone" % name)

    # Deleting a file that something still points at trades dead weight for a
    # broken link, so assert nothing references them either. A stylesheet
    # url() and a script fetch reach a deleted file exactly as an href does,
    # so the scan covers CSS and JS, not only the pages.
    for path in HTML_PAGES + [STYLE_CSS, MAIN_JS]:
        source = read(path)
        if source is None:
            continue
        for name in LEFTOVER_TEMPLATE_FILES:
            check(
                name not in source,
                "%s does not reference %s" % (path.relative_to(ROOT), name),
            )


def check_resume_declares_no_unloaded_font():
    """A quoted family the page never loads is a declaration that does nothing.

    Generic families (sans-serif, serif, monospace) are unquoted by CSS
    convention and are always available, so only quoted names are checked.
    Each one has to be backed by an @font-face on the page or a stylesheet
    link that names it, or the browser silently falls through to the next
    entry in the stack and the declaration misstates what actually renders.

    Two limits, both deliberate. A linked stylesheet is matched by its URL
    containing the family name, with the space spelled either as + or as
    %20, since that is as far as a source-level check can see without
    fetching and parsing the stylesheet. And a family defined inside an
    already-linked external stylesheet, such as FontAwesome in
    css/font-awesome.min.css, is recognized only through FONT_FAMILIES_FROM
    below. Add an entry there rather than loosening the match when a page
    starts declaring a family that some other stylesheet provides.
    """
    print("\nresume.html declares no font it does not load")

    source = read_or_fail(RESUME)
    if source is None:
        return

    families = set()
    for declaration in re.findall(r"font-family\s*:\s*([^;}]+)", source):
        for single, double in re.findall(r"'([^']+)'|\"([^\"]+)\"", declaration):
            families.add((single or double).strip())

    if not families:
        print("  PASS  resume.html names no webfont family it would have to load")
        return

    for family in sorted(families):
        face = re.search(
            r"@font-face[^}]*font-family\s*:\s*['\"]?" + re.escape(family),
            source,
            re.I | re.S,
        )
        # A Google Fonts href spells the space as +, a percent-encoded one
        # spells it %20. Accept either rather than only the first.
        spellings = {
            family,
            family.replace(" ", "+"),
            family.replace(" ", "%20"),
        }
        link = any(
            re.search(r'<link[^>]+href="[^"]*' + re.escape(spelling), source, re.I)
            for spelling in spellings
        )
        # A family that a linked stylesheet defines rather than the page.
        provider = FONT_FAMILIES_FROM.get(family.lower())
        provided = provider is not None and provider in source

        check(
            face is not None or link or provided,
            "resume.html loads the '%s' family it declares" % family,
        )


def main():
    check_contact_form_returns_visitor()
    check_thanks_page_is_a_complete_document()
    check_no_dead_form_error_markup()
    check_contact_form_spacing_is_declared()
    check_list_markup_is_balanced()
    check_leftover_template_files_are_gone()
    check_resume_declares_no_unloaded_font()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
