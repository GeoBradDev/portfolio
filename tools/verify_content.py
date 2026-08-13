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


def main():
    check_contact_form_returns_visitor()
    check_thanks_page_is_a_complete_document()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
