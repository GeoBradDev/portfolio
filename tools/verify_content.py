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
CNAME = ROOT / "CNAME"

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
        check(
            parsed.netloc == host,
            "_next points at the host CNAME names (%s), not %s"
            % (host, parsed.netloc or "a relative path"),
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
        for token in ("form-message", "name-error", "email-error", "message-error"):
            check(
                token not in source,
                "index.html no longer carries the dead %s element" % token,
            )

    css = read_or_fail(STYLE_CSS)
    if css is not None:
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
    print("\nEvery list item in index.html is closed")

    source = read_or_fail(INDEX)
    if source is None:
        return

    parser = ListMarkup()
    parser.feed(source)
    if parser.problems:
        for problem in parser.problems:
            fail("index.html %s" % problem)
    else:
        print("  PASS  index.html closes every <li>")


def check_leftover_template_files_are_gone():
    print("\nLeftover template files are gone")

    for name in LEFTOVER_TEMPLATE_FILES:
        check(not (ROOT / name).exists(), "%s is gone" % name)

    # Deleting a file that something still points at trades dead weight for a
    # broken link, so assert nothing references them either.
    for page in (INDEX, RESUME, THANKS):
        source = read(page)
        if source is None:
            continue
        for name in LEFTOVER_TEMPLATE_FILES:
            check(
                name not in source,
                "%s does not reference %s" % (page.relative_to(ROOT), name),
            )


def check_resume_declares_no_unloaded_font():
    """A quoted family the page never loads is a declaration that does nothing.

    Generic families (sans-serif, serif, monospace) are unquoted by CSS
    convention and are always available, so only quoted names are checked.
    Each one has to be backed by an @font-face on the page or a stylesheet
    link that names it, or the browser silently falls through to the next
    entry in the stack and the declaration misstates what actually renders.
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
        link = re.search(
            r'<link[^>]+href="[^"]*' + re.escape(family.replace(" ", "+")),
            source,
            re.I,
        )
        check(
            face is not None or link is not None,
            "resume.html loads the '%s' family it declares" % family,
        )


def main():
    check_contact_form_returns_visitor()
    check_thanks_page_is_a_complete_document()
    check_no_dead_form_error_markup()
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
