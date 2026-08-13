# Content and Navigation Implementation Plan (issue 18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return contact-form visitors to the site after submit, and clear the dead markup, dead CSS, and leftover template files that issue 18 catalogued.

**Architecture:** The site has no test runner. Its test harness is a set of standalone Python verifier scripts under `tools/`, one per issue: `verify_assets.py` (issue 15), `verify_interactivity.py` (issue 16), `verify_security.py` (issue 17). This plan follows that pattern and adds `tools/verify_content.py` for issue 18. Every task writes its check into that file first, watches it fail, then changes the site to make it pass. No build step is added and no dependency is introduced.

**Tech Stack:** Vanilla HTML5, CSS3, jQuery 3.7.1, Bootstrap 3.3.7, FormSubmit for the contact form, Python 3 standard library for the verifiers.

## Global Constraints

- No emojis anywhere: code, markup, comments, commit messages, PR text.
- No em dashes in any text output. Use commas, periods, or colons.
- JavaScript only, never TypeScript.
- `tools/` scripts are standard library only, run by hand, never a build step.
- All four verifiers must exit 0 at the end of every task: `verify_assets.py`, `verify_security.py`, `verify_interactivity.py`, `verify_content.py`.
- The site host is whatever `CNAME` contains. Today that is `www.geobrad.dev`. Read it, never hardcode it in a verifier.
- Font Awesome is 4.7.0 served locally. Use bare `fa fa-*` classes. The FA5/FA6 `fas`/`fab`/`far` classes render nothing here and `verify_security.py` rejects them.
- `verify_security.py` discovers pages with a glob over `*.html` at the repo root, so any new page is swept the moment it is created.

## Scope: what this plan does and does not do

Issue 18 lists ten findings and seven acceptance criteria. Five findings were already resolved by the work on issues 15, 16, and 17. Two acceptance criteria were declined by the site owner on 2026-08-12.

| Issue 18 item | Disposition in this plan |
|---|---|
| 1. `resume.html` orphaned | **Declined by owner.** The resume is sent on request. It stays reachable by URL and unlinked. |
| 2. `privacy.html` orphaned | **Declined by owner.** That policy belongs to a different project and is hosted here only so its existing URL keeps resolving. It stays in the tree, unlinked and unmodified. |
| 3. Stale copyright year | Already fixed. `index.html:445` plus `index.html:468-469` set it from `new Date().getFullYear()`. |
| 4. Job title inconsistent | Already fixed. Both pages read "Geospatial Software Engineer" throughout. |
| 5. Resume section ordering | Moot. The resume was rewritten: NGA is now `2010 - Sep 2025` and Carbon Solutions is current and listed first. |
| 6. Contact form strands the visitor | **Task 1.** |
| 6a. Dead `#form-message` and `.*-error` markup | **Task 2.** |
| 7. Leftover template files | **Task 4.** Six of eight were deleted in issue 15. `mail/contact.php` and `video/video.mp4` remain. |
| 8. Template attribution | No change. `js/main.js` was rewritten in issue 16 and its ThemeForest header is gone. `css/style.css:1-6` still carries the IMOZAR/PhyDev header, which is accurate provenance for a template the site still uses. No "Bamboo" reference survives anywhere in the tree. |
| 9. Malformed footer markup | **Task 3.** |
| 10. `resume.html` declares Roboto, never loads it | **Task 5.** |

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tools/verify_content.py` | Create. The issue 18 gate: contact form return path, the thanks page being a complete document, absence of dead form markup and CSS, balanced `<li>` markup, leftover template files gone, no unloaded webfont on the resume. Also the written record of the two declined criteria. | 1-5 |
| `thanks.html` | Create. Post-submit confirmation page. Standalone, matches the site palette, no JavaScript. | 1 |
| `index.html` | Modify. Add `_next` and `_subject` to the contact form, delete four dead elements, close one `<li>`. | 1, 2, 3 |
| `css/style.css` | Modify. Delete the dead validation rules at 1126-1147. | 2 |
| `resume.html` | Modify. Drop `'Roboto'` from the body font stack. | 5 |
| `tools/verify_security.py` | Modify. Syntax-gate inline scripts on every discovered page, not just `index.html` and `resume.html`, so `thanks.html` is not silently exempt. | 1 |
| `mail/contact.php`, `video/video.mp4` | Delete. | 4 |

---

### Task 1: Contact form returns the visitor to the site

FormSubmit redirects to its own confirmation page on `formsubmit.co` unless the form carries a `_next` field. The visitor never comes back. This task adds `_next` and a page for it to land on, and closes the gate gap that would let a new page skip the inline-script syntax check.

**Files:**
- Create: `tools/verify_content.py`
- Create: `thanks.html`
- Modify: `index.html` (the `<form id="contact-form">` block, currently lines 387-407)
- Modify: `tools/verify_security.py:328` (`check_inline_script_syntax`)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `tools/verify_content.py` with module-level `ROOT`, `INDEX`, `RESUME`, `THANKS`, `STYLE_CSS`, `CNAME`, the `failures` list, and the helpers `fail(message)`, `check(condition, message) -> bool`, `read(path) -> str | None`, `read_or_fail(path) -> str | None`, `contact_form(source) -> str | None`, `hidden_value(form, name) -> str | None`, and `site_host() -> str | None`. Tasks 2 through 5 add further `check_*` functions to this file and register them in `main()`.

- [ ] **Step 1: Write the failing test**

Create `tools/verify_content.py`:

```python
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
            "_next stays on %s, not %s" % (host, parsed.netloc or "a relative path"),
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
        re.search(r'<meta[^>]+charset', source, re.I) is not None,
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_content.py`

Expected: exit 1. `the contact form carries a _next redirect` FAILs, and every check under `thanks.html is a complete document` FAILs because the file does not exist.

- [ ] **Step 3: Add the hidden fields to the contact form**

In `index.html`, inside `<form id="contact-form">`, immediately after the `_honey` input at line 404, add:

```html
                    <!-- Without _next, FormSubmit's confirmation page is on
                         formsubmit.co and the visitor has no way back. The
                         URL has to be absolute for FormSubmit to honor it. -->
                    <input type="hidden" name="_next" value="https://www.geobrad.dev/thanks.html">
                    <input type="hidden" name="_subject" value="New contact from GeoBrad.dev">
```

- [ ] **Step 4: Create thanks.html**

Create `thanks.html`. Standalone and self-contained apart from the same Lato stylesheet `index.html` loads, so the type matches the site. No JavaScript, which also keeps it off the one gate that would not have seen it. Palette copied from `css/style.css`: body `#484848` on `#fff`, headings `#333`, the button is the site's `.submit-btn`, `#333` filled inverting to transparent with a `#111` label on hover.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Message Sent | Brad Stricherz</title>
    <meta name="robots" content="noindex">
    <link href="https://fonts.googleapis.com/css?family=Lato:400,400i,700,700i" rel="stylesheet">
    <link rel="icon" href="img/favicon.ico">
    <style>
        body {
            margin: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 30px;
            box-sizing: border-box;
            font-family: 'Lato', sans-serif;
            font-size: 15px;
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
            margin: 0 0 14px;
            font-size: 32px;
            font-weight: 700;
            line-height: 1.2;
            color: #333;
        }

        p {
            margin: 0 0 30px;
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
            transition: all .4s;
        }

        .back-btn:hover,
        .back-btn:focus {
            color: #111;
            background-color: transparent;
        }
    </style>
</head>
<body>

<div class="panel">
    <h1>Message sent</h1>
    <p>Thanks for reaching out. I read everything that comes through here and I will get back to you soon.</p>
    <a class="back-btn" href="/">Back to GeoBrad.dev</a>
</div>

</body>
</html>
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python3 tools/verify_content.py`

Expected: exit 0, `All checks passed.`

- [ ] **Step 6: Close the inline-script gate gap for new pages**

`verify_security.check_inline_script_syntax` iterates `(INDEX, RESUME)`, so `thanks.html` would be exempt from the syntax gate even though `verify_security.py` discovers pages with a glob everywhere else. `thanks.html` ships no script today, but the exemption is the bug, not the empty result. Replace the loop at `tools/verify_security.py:328` with one over `HTML_PAGES`, keeping the "has an inline script to check" assertion only for the two pages that are expected to carry one:

```python
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        blocks = inline.findall(source)
        name = path.relative_to(ROOT)

        # index.html and resume.html are expected to carry inline script, so
        # losing it there means the extraction pattern broke. A page that
        # legitimately has none, thanks.html or the Termly privacy paste,
        # must not fail for that.
        if path in (INDEX, RESUME):
            if not check(bool(blocks), "%s has an inline script to check" % name):
                continue
        elif not blocks:
            print("  skip  %s has no inline script" % name)
            continue

        for number, body in enumerate(blocks, start=1):
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

- [ ] **Step 7: Run the whole gate**

Run each in turn from the repo root:

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_interactivity.py
python3 tools/verify_content.py
```

Expected: all four exit 0. `verify_security.py` now prints `skip  thanks.html has no inline script` and `skip  privacy.html has no inline script`.

- [ ] **Step 8: Commit**

```bash
git add tools/verify_content.py tools/verify_security.py thanks.html index.html
git commit -m "fix: return contact form visitors to the site after submit"
```

---

### Task 2: Remove the dead form validation markup and CSS

`#form-message` and the three `.*-error` spans have nothing that writes to them. The `js/main.js` block that used to was deleted in issue 16, and the form relies on the `required` attributes and FormSubmit. Their CSS is dead for the same reason, including a `.success` rule no element in the tree has ever carried.

**Files:**
- Modify: `tools/verify_content.py` (add one `check_*`, register it in `main()`)
- Modify: `index.html:391,396,401,403`
- Modify: `css/style.css:1126-1147`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `INDEX`, `STYLE_CSS` from Task 1.
- Produces: `check_no_dead_form_error_markup()`.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_content.py`, above `main()`:

```python
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
```

Register it in `main()`, after `check_thanks_page_is_a_complete_document()`:

```python
    check_no_dead_form_error_markup()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_content.py`

Expected: exit 1, with 10 FAIL lines under `No dead contact form validation markup`.

- [ ] **Step 3: Delete the markup**

In `index.html`, delete these four lines outright:

```html
                        <span class="name-error text-center mb-30"></span>
                        <span class="email-error text-center mb-30"></span>
                        <span class="message-error text-center mb-30"></span>
                    <div id="form-message" class="error mb-30 text-center"></div>
```

- [ ] **Step 4: Delete the CSS**

In `css/style.css`, delete lines 1126-1147, which is exactly these three rules and the blank lines between them:

```css
.name-error,
.email-error,
.message-error,
.error {
    display: block;
    margin-top: 8px;
    font-size: 14px;
    color: #ff2828;
}

.success {
    display: block;
    margin-top: 8px;
    font-size: 14px;
    color: #1e9402;
}

#form-message {
    float: left;
    width: 100%;
}
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python3 tools/verify_content.py`

Expected: exit 0.

- [ ] **Step 6: Run the whole gate**

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_interactivity.py
python3 tools/verify_content.py
```

Expected: all four exit 0.

- [ ] **Step 7: Commit**

```bash
git add tools/verify_content.py index.html css/style.css
git commit -m "fix: remove dead contact form validation markup and CSS"
```

---

### Task 3: Close the unclosed footer list item

The Instagram `<li>` in the footer social list never closes before the LinkedIn `<li>` opens. Browsers auto-close it, so nothing renders wrong today, but the check below is a general one over the whole page rather than a spot fix, so a future unclosed item fails the gate instead of relying on the parser's goodwill.

**Files:**
- Modify: `tools/verify_content.py` (add one `HTMLParser` subclass and one `check_*`, register it in `main()`)
- Modify: `index.html:436-438`

**Interfaces:**
- Consumes: `check`, `fail`, `read_or_fail`, `INDEX`, and the `HTMLParser` import from Task 1.
- Produces: `ListMarkup(HTMLParser)` with attribute `problems` (a list of strings), and `check_list_markup_is_balanced()`.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_content.py`, above `main()`:

```python
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
```

Register it in `main()`, after `check_no_dead_form_error_markup()`:

```python
    check_list_markup_is_balanced()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_content.py`

Expected: exit 1, with one line reading `index.html line NNN: <li> opens while the previous <li> is still open`. The reported line is the LinkedIn `<li>` in the footer social list. Do not assert a fixed number here: tasks 1 and 2 both add and remove lines above it, so the exact value depends on how many of them have landed.

- [ ] **Step 3: Close the tag**

In `index.html`, the footer social list currently reads:

```html
                    <li><a class="effect" href="https://www.instagram.com/GeoBradDev/" target="_blank"><i
                            class="fa fa-instagram"></i></a>
                    <li><a class="effect" href="https://www.linkedin.com/in/brad-stricherz-944999349/"
```

Change it to:

```html
                    <li><a class="effect" href="https://www.instagram.com/GeoBradDev/" target="_blank"><i
                            class="fa fa-instagram"></i></a>
                    </li>
                    <li><a class="effect" href="https://www.linkedin.com/in/brad-stricherz-944999349/"
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 tools/verify_content.py`

Expected: exit 0, with `PASS  index.html closes every <li>`.

- [ ] **Step 5: Run the whole gate**

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_interactivity.py
python3 tools/verify_content.py
```

Expected: all four exit 0.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_content.py index.html
git commit -m "fix: close the unclosed footer list item"
```

---

### Task 4: Delete the leftover template files

Six of the eight files issue 18 listed were deleted in issue 15. Two remain. `mail/contact.php` is a PHP mail handler on a GitHub Pages site, which cannot execute PHP, for a form that posts to FormSubmit instead. `video/video.mp4` is 330 KB referenced from nowhere. Neither is reachable by any code path, and neither directory holds anything else.

**Files:**
- Modify: `tools/verify_content.py` (add one `check_*`, register it in `main()`)
- Delete: `mail/contact.php`
- Delete: `video/video.mp4`

**Interfaces:**
- Consumes: `check`, `read`, `ROOT` from Task 1.
- Produces: `check_leftover_template_files_are_gone()`.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_content.py`, above `main()`:

```python
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
```

Register it in `main()`, after `check_list_markup_is_balanced()`:

```python
    check_leftover_template_files_are_gone()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_content.py`

Expected: exit 1, with `mail/contact.php is gone` and `video/video.mp4 is gone` FAILing. The six reference checks pass already.

- [ ] **Step 3: Delete the files**

```bash
git rm mail/contact.php video/video.mp4
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 tools/verify_content.py`

Expected: exit 0.

- [ ] **Step 5: Run the whole gate**

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_interactivity.py
python3 tools/verify_content.py
```

Expected: all four exit 0.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_content.py
git commit -m "fix: delete the last two unused template files"
```

---

### Task 5: Stop the resume declaring a font it never loads

`resume.html:10` sets `font-family: 'Roboto', sans-serif` while the page loads no `@font-face` and no font stylesheet, so it silently falls back to the system sans-serif for everyone without Roboto installed locally. Dropping the name is the honest fix: it makes the declaration say what the page actually renders, and it adds no third party request to a document that is regularly printed to PDF.

**Files:**
- Modify: `tools/verify_content.py` (add one `check_*`, register it in `main()`)
- Modify: `resume.html:10`

**Interfaces:**
- Consumes: `check`, `read_or_fail`, `RESUME` from Task 1.
- Produces: `check_resume_declares_no_unloaded_font()`.

- [ ] **Step 1: Write the failing test**

Add to `tools/verify_content.py`, above `main()`:

```python
def check_resume_declares_no_unloaded_font():
    """A quoted family the page never loads is a declaration that does nothing.

    Generic families (sans-serif, serif, monospace) are unquoted by CSS
    convention and are always available, so only quoted names are checked.
    Each one has to be backed by an @font-face on the page or a stylesheet
    link that names it, or the browser silently falls through to the next
    entry in the stack and the declaration is a lie about what renders.
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
```

Register it in `main()`, after `check_leftover_template_files_are_gone()`:

```python
    check_resume_declares_no_unloaded_font()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 tools/verify_content.py`

Expected: exit 1, with `resume.html loads the 'Roboto' family it declares` FAILing.

- [ ] **Step 3: Drop the unloaded family**

In `resume.html`, change line 10 from:

```css
            font-family: 'Roboto', sans-serif;
```

to:

```css
            /* No webfont is loaded here on purpose. This page is printed to
               PDF regularly, so it stays free of third party requests, and
               naming a family the page never fetches only misstates what
               actually renders. */
            font-family: sans-serif;
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python3 tools/verify_content.py`

Expected: exit 0, with `PASS  resume.html names no webfont family it would have to load`.

- [ ] **Step 5: Run the whole gate**

```bash
python3 tools/verify_assets.py
python3 tools/verify_security.py
python3 tools/verify_interactivity.py
python3 tools/verify_content.py
```

Expected: all four exit 0.

- [ ] **Step 6: Commit**

```bash
git add tools/verify_content.py resume.html
git commit -m "fix: stop resume.html declaring a font it never loads"
```

---

## After the tasks

Phases 5 through 9 of the /work-issue workflow still apply: code review scaled to the High risk tier, the full gate plus a live drive of the contact form, verification, the CLAUDE.md reconciliation (it needs the `verify_content.py` section, the `thanks.html` entry, the corrected claim that dead CSS cleanup is "tracked separately in issue #18", and the note that `resume.html` and `privacy.html` are unlinked on purpose), and the PR.

The live drive must not submit the real form. Submitting posts to FormSubmit and sends actual mail, which is an outward-facing action. Drive the local page, confirm the hidden fields are in the submitted payload with the browser's own form serialization, and load `thanks.html` directly. Ask before sending a real submission.
