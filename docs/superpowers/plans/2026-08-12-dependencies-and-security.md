# Dependencies and Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close issue #17: retire jQuery 2.2.4 and its CVEs, stop remote GitHub data from
reaching `innerHTML` or an `href` unescaped, and remove the dead mixed-content, IE8, and
duplicate-Font-Awesome references.

**Architecture:** The site has no build step, so every change is a direct source edit. The
one new file is `tools/verify_security.py`, a standard-library verifier in the same shape as
the existing `verify_assets.py` and `verify_interactivity.py`. It encodes issue #17's
acceptance criteria as source-level assertions, so it is written first, watched to fail, and
then driven to green. The portfolio card renderer stops interpolating strings and builds DOM
nodes with `document.createElement` and `textContent`; a single `safeUrl()` helper gates every
place a repo-supplied URL becomes navigable.

**Tech Stack:** Vanilla HTML5, CSS3, JavaScript, jQuery 3.7.1, Bootstrap 3.3.7, Font Awesome
4.7.0 (local), Python 3 standard library for the verifiers.

## Global Constraints

- No build system. No npm, no bundler, no new runtime dependency. `tools/` scripts are run by
  hand and must use the Python standard library only.
- No emojis and no em dashes in any file, comment, commit message, or PR text.
- JavaScript only. Never TypeScript.
- The existing gate must stay green: `python3 tools/verify_assets.py` and
  `python3 tools/verify_interactivity.py` both exit 0 after every task.
- Homepage transfer budget is 1024 KB, hero budget is 300 KB, both enforced by
  `verify_assets.py`. Current homepage total is 682.6 KB.
- jQuery target version is exactly **3.7.1**, fetched from `https://code.jquery.com/jquery-3.7.1.min.js`.
- Font Awesome is unified on the **locally bundled 4.7.0** at `css/font-awesome.min.css`. No
  CDN-hosted icon assets remain anywhere in the repo.
- Bootstrap 3 end-of-life (issue #17 finding 7) is explicitly **out of scope**; the issue defers
  it. Dead `.home-carousel` / `.owl-*` CSS beyond the three `placehold.it` rules is issue #18's
  scope, not this plan's.
- Only `index.html` loads `js/main.js`. `resume.html` and `privacy.html` are standalone.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `tools/verify_security.py` | Create | Encodes the six acceptance criteria of issue #17 as source-level checks. Standard library only, exits 0 or 1. |
| `js/jquery.min.js` | Replace | jQuery 2.2.4 to 3.7.1. |
| `index.html` | Modify | Remove the IE8 conditional block; rebuild portfolio cards with DOM APIs; scheme-validate repo URLs. |
| `css/style.css` | Modify | Delete the three `http://placehold.it` background rules. |
| `resume.html` | Modify | Drop both cdnjs Font Awesome tags, link the local FA 4.7.0 stylesheet, rewrite 11 icon classes to FA4 syntax. |
| `CLAUDE.md` | Modify | Correct the jQuery version claim, record the Font Awesome decision and the new verifier. |

---

### Task 1: The security verifier

This task creates the failing test for everything that follows. It is one task because the six
checks share a file, a reporting helper, and an exit contract; a reviewer would accept or reject
the verifier as a whole.

**Files:**
- Create: `tools/verify_security.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: an executable `python3 tools/verify_security.py` that exits 0 when all six issue #17
  criteria hold and 1 otherwise, printing one `PASS` or `FAIL` line per check. Tasks 2 through 6
  each drive one or more of its checks from FAIL to PASS. Internal helpers other tasks do not
  call: `fail(message)`, `check(condition, message)`, `read(path)`.

One check does not come from the issue. `check_inline_script_syntax` exists because
`verify_interactivity.py` syntax-checks `js/main.js` but nothing checks the inline `<script>` in
`index.html`, and Task 3 rewrites about 90 lines of it. Without this the first sign of a typo
would be a blank portfolio section in a browser.

- [ ] **Step 1: Write the failing test**

Create `tools/verify_security.py`:

```python
#!/usr/bin/env python3
"""Check the dependency and security criteria from issue 17.

Run from the repository root:

    python3 tools/verify_security.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.

Source-level only. That the escaped card actually renders, and that a hostile
homepage URL is actually refused at runtime, has to be driven in a browser.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RESUME = ROOT / "resume.html"
PRIVACY = ROOT / "privacy.html"
STYLE_CSS = ROOT / "css" / "style.css"
JQUERY = ROOT / "js" / "jquery.min.js"
CLAUDE_MD = ROOT / "CLAUDE.md"

# jQuery below this is affected by CVE-2020-11022, CVE-2020-11023 (XSS via
# .html()/.append(), fixed in 3.5.0) and CVE-2019-11358 (prototype pollution
# via $.extend(true, ...), fixed in 3.4.0).
JQUERY_MIN_MAJOR = 3
JQUERY_MIN_MINOR = 5

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
    return path.read_text(encoding="utf-8", errors="replace")


def check_jquery_version():
    print("\njQuery is patched against the known CVEs")

    if not check(JQUERY.exists(), "js/jquery.min.js exists"):
        return

    banner = read(JQUERY)[:200]
    match = re.search(r"jQuery v(\d+)\.(\d+)\.(\d+)", banner)
    if not check(match is not None, "js/jquery.min.js declares a version in its banner"):
        return

    major, minor, patch = (int(g) for g in match.groups())
    version = "%d.%d.%d" % (major, minor, patch)
    check(
        (major, minor) >= (JQUERY_MIN_MAJOR, JQUERY_MIN_MINOR),
        "js/jquery.min.js is %s, at or above the %d.%d floor"
        % (version, JQUERY_MIN_MAJOR, JQUERY_MIN_MINOR),
    )

    # CLAUDE.md claimed 3.x while 2.2.4 shipped for two years. Assert the
    # documented version against the file so the claim cannot drift again.
    doc = read(CLAUDE_MD)
    check(
        version in doc,
        "CLAUDE.md names the shipped jQuery version (%s)" % version,
    )


def check_no_unescaped_interpolation():
    print("\nNo remote GitHub data reaches innerHTML")

    source = read(INDEX)

    # Every repo field the GitHub API supplies and the card renderer uses.
    remote_fields = [
        "repo.name",
        "repo.description",
        "repo.homepage",
        "repo.html_url",
        "repo.language",
        "repo.stargazers_count",
    ]

    # A template placeholder holding a repo field, anywhere in the file.
    for field in remote_fields:
        pattern = r"\$\{\s*" + re.escape(field)
        check(
            re.search(pattern, source) is None,
            "index.html does not interpolate %s into a template literal" % field,
        )

    check(
        "safeUrl" in source,
        "index.html defines a safeUrl helper for repo-supplied URLs",
    )


def check_repo_urls_are_scheme_validated():
    print("\nRepo-supplied URLs are scheme validated before use")

    source = read(INDEX)

    # Both navigable sinks: the anchor href and the whole-card window.open.
    check(
        re.search(r"window\.open\(\s*repo\.", source) is None,
        "index.html does not pass a raw repo field to window.open",
    )
    check(
        re.search(r"href\s*=\s*repo\.", source) is None,
        "index.html does not assign a raw repo field to an href",
    )
    check(
        "https:" in source,
        "index.html names the https: scheme it allows",
    )


def check_no_plain_http_assets():
    print("\nNo plain-http asset references")

    # An http:// URL inside a url(), src=, or href= is a mixed-content request
    # on an https site. The SVG xmlns namespace in index.html is an identifier,
    # never fetched, so it is not matched here.
    asset_http = re.compile(r"""(?:url\(|src\s*=\s*|href\s*=\s*)['"(]?\s*http://""")

    for path in (STYLE_CSS, INDEX, RESUME, PRIVACY):
        hits = asset_http.findall(read(path))
        check(
            not hits,
            "%s has no http:// asset reference" % path.relative_to(ROOT),
        )

    check(
        "placehold.it" not in read(STYLE_CSS),
        "css/style.css no longer references placehold.it",
    )


def check_no_ie_conditional_shims():
    print("\nNo IE conditional comment shims")

    source = read(INDEX)
    check("[if lt IE" not in source, "index.html has no IE conditional comment")
    check("html5shiv" not in source, "index.html does not load html5shiv")
    check("respond.min.js" not in source, "index.html does not load Respond.js")
    check("maxcdn.com" not in source, "index.html does not reference the dead MaxCDN host")


def check_font_awesome_is_single_local_version():
    print("\nFont Awesome is one local version site-wide")

    pages = {"index.html": read(INDEX), "resume.html": read(RESUME), "privacy.html": read(PRIVACY)}

    for name, source in pages.items():
        check(
            "cdnjs.cloudflare.com" not in source,
            "%s loads no asset from cdnjs" % name,
        )
        # FA5 and FA6 split the base class into fas/far/fab. FA4 uses a bare
        # fa. Finding either style class means two majors are in play.
        fa_six = re.search(r'class="[^"]*\bfa[sbrl]\s+fa-', source)
        check(
            fa_six is None,
            "%s uses no FA5/FA6 style class (fas, fab, far, fal)" % name,
        )

    for name in ("index.html", "resume.html"):
        source = pages[name]
        if "fa-" not in source:
            continue
        check(
            "css/font-awesome.min.css" in source,
            "%s links the local css/font-awesome.min.css" % name,
        )


def check_inline_script_syntax():
    """The portfolio renderer lives inline, where node --check cannot see it.

    verify_interactivity.py syntax-checks js/main.js, but the ~90 lines that
    build the portfolio cards sit in an inline <script> in index.html and had
    no gate at all. Extract every attribute-less <script> block and check it.
    node is a convenience here, never a project dependency.
    """
    print("\nInline scripts parse")

    if shutil.which("node") is None:
        print("  skip  node not found, cannot syntax-check inline scripts")
        return

    inline = re.compile(r"<script\s*>(.*?)</script>", re.S)

    for path in (INDEX, RESUME):
        blocks = inline.findall(read(path))
        name = path.relative_to(ROOT)

        if not check(bool(blocks), "%s has an inline script to check" % name):
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


def main():
    check_jquery_version()
    check_no_unescaped_interpolation()
    check_repo_urls_are_scheme_validated()
    check_no_plain_http_assets()
    check_no_ie_conditional_shims()
    check_font_awesome_is_single_local_version()
    check_inline_script_syntax()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tools/verify_security.py; echo "exit=$?"`

Expected: `exit=1`, with FAIL lines covering every criterion, including
`js/jquery.min.js is 2.2.4, at or above the 3.5 floor`, six
`index.html does not interpolate repo.* into a template literal` failures,
`css/style.css has no http:// asset reference`, `index.html has no IE conditional comment`,
and `resume.html loads no asset from cdnjs`.

The `Inline scripts parse` section should already PASS; it is a guard for Task 3, not a
criterion of the issue. If it FAILs now, stop: the extraction regex is wrong, not the site.

- [ ] **Step 3: Write minimal implementation**

None. This task is the failing test; Tasks 2 through 6 are its implementation.

- [ ] **Step 4: Confirm the existing gate is unaffected**

Run: `python3 tools/verify_assets.py > /dev/null; echo "assets=$?"; python3 tools/verify_interactivity.py > /dev/null; echo "interactivity=$?"`

Expected: `assets=0` and `interactivity=0`. The new file adds no reference to any page.

- [ ] **Step 5: Commit**

```bash
git add tools/verify_security.py
git commit -m "test: add verifier for issue 17 dependency and security criteria"
```

---

### Task 2: Upgrade jQuery to 3.7.1

**Files:**
- Modify: `js/jquery.min.js` (replace wholesale)

**Interfaces:**
- Consumes: the `check_jquery_version` check from Task 1.
- Produces: `js/jquery.min.js` at version 3.7.1. `js/main.js` and `js/bootstrap.min.js` are
  unchanged; Bootstrap 3.3.7 is the release that added jQuery 3 support, and every jQuery call
  in `main.js` (`.fadeOut`, `.animate`, `.toggleClass`, `.offset`, `.outerHeight`, `.each`,
  `.data`, `.on`) is unchanged API in 3.7.1.

- [ ] **Step 1: Confirm the check currently fails**

Run: `python3 tools/verify_security.py 2>&1 | grep jquery`

Expected: a FAIL line reporting 2.2.4 against the 3.5 floor.

- [ ] **Step 2: Fetch 3.7.1 and verify its integrity before installing**

The published SRI digest for jQuery 3.7.1 minified is
`sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=`. Download to a temporary path, compare,
and only then move it into place. Do not skip the comparison; this file executes on every page
load.

```bash
curl -fsSL https://code.jquery.com/jquery-3.7.1.min.js -o /tmp/jquery-3.7.1.min.js
python3 - <<'PY'
import base64, hashlib, pathlib, sys
data = pathlib.Path("/tmp/jquery-3.7.1.min.js").read_bytes()
digest = "sha256-" + base64.b64encode(hashlib.sha256(data).digest()).decode()
expected = "sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo="
print("computed", digest)
print("expected", expected)
sys.exit(0 if digest == expected else 1)
PY
echo "integrity=$?"
```

Expected: `integrity=0` and the two digests printed identical. If they differ, stop and report;
do not install the file.

- [ ] **Step 3: Install it**

```bash
cp /tmp/jquery-3.7.1.min.js js/jquery.min.js
head -c 80 js/jquery.min.js
```

Expected banner: `/*! jQuery v3.7.1 | (c) OpenJS Foundation and other contributors | jquery.org/license */`

- [ ] **Step 4: Run the checks**

Run: `python3 tools/verify_security.py 2>&1 | grep -i jquery`

Expected: `PASS  js/jquery.min.js is 3.7.1, at or above the 3.5 floor`. The
`CLAUDE.md names the shipped jQuery version (3.7.1)` check still FAILs; Task 6 fixes it.

Run: `python3 tools/verify_assets.py > /dev/null; echo "assets=$?"; python3 tools/verify_interactivity.py > /dev/null; echo "interactivity=$?"`

Expected: both 0. The homepage budget drops, since 3.7.1 minified is smaller than the 132 KB
2.2.4 file on disk.

- [ ] **Step 5: Commit**

```bash
git add js/jquery.min.js
git commit -m "fix: upgrade jQuery from 2.2.4 to 3.7.1 to clear known CVEs"
```

---

### Task 3: Build portfolio cards from DOM nodes, not strings

This is the security fix at the heart of the issue and the one task with real behavior to
preserve. The rendered markup, the class names, and the click behavior must come out identical
for well-formed repo data; only the construction path changes.

**Files:**
- Modify: `index.html:515-573` (the `portfolioRepos.forEach` block and the click-handler block
  that follows it)

**Interfaces:**
- Consumes: Task 1's `check_no_unescaped_interpolation` and
  `check_repo_urls_are_scheme_validated`.
- Produces: two module-scope helpers inside the existing inline `<script>`:
  - `safeUrl(value)` returns the string `value` when it parses as an absolute URL whose protocol
    is exactly `https:`, and `null` otherwise. Accepts anything, never throws.
  - `el(tag, className, text)` returns an `HTMLElement` with `className` applied when truthy and
    `textContent` set when `text` is not `undefined`.

- [ ] **Step 1: Confirm the checks currently fail**

Run: `python3 tools/verify_security.py 2>&1 | grep -e interpolate -e safeUrl -e window.open -e "href"`

Expected: FAIL lines for all six `repo.*` fields, for the missing `safeUrl` helper, and for
`index.html does not pass a raw repo field to window.open`.

- [ ] **Step 2: Add the two helpers**

In `index.html`, immediately after the `portfolioContainer` declaration
(`const portfolioContainer = document.getElementById("github-projects");`), insert:

```javascript
    // Repo fields come from the GitHub API, so nothing below may reach the DOM
    // as markup. Every text node is set with textContent, and every navigable
    // URL goes through safeUrl first.
    //
    // A repo's homepage is whatever its owner typed into a text box. Left
    // unchecked it lands in an href and in window.open, and both of those run
    // a javascript: URL in this page's origin. Allow https and nothing else:
    // http would be mixed content on this site anyway.
    function safeUrl(value) {
        if (typeof value !== 'string' || value === '') return null;
        let parsed;
        try {
            parsed = new URL(value);
        } catch (err) {
            return null;
        }
        return parsed.protocol === 'https:' ? parsed.href : null;
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }
```

- [ ] **Step 3: Replace the card renderer**

Replace the whole `portfolioRepos.forEach((repo, index) => { ... });` block (the one whose body
assigns `card.innerHTML`) with:

```javascript
            portfolioRepos.forEach((repo) => {
                const demoUrl = safeUrl(repo.homepage);
                const codeUrl = safeUrl(repo.html_url);

                const item = el("div", "col-sm-6 col-md-4 portfolio-item");
                const cardEl = el("div", "portfolio-card");
                const inner = el("div", "portfolio-card-inner");
                const content = el("div", "portfolio-content");

                const header = el("div", "portfolio-header");
                header.appendChild(el("h3", "portfolio-title", repo.name));
                const meta = el("div", "portfolio-meta");
                meta.appendChild(el("span", "portfolio-language", repo.language || "Code"));
                meta.appendChild(el("span", "portfolio-stars", "★ " + repo.stargazers_count));
                header.appendChild(meta);
                content.appendChild(header);

                const description = el("div", "portfolio-description");
                description.appendChild(el("p", null, repo.description || "No description available"));
                content.appendChild(description);

                const footer = el("div", "portfolio-footer");
                const links = el("div", "portfolio-links");

                if (demoUrl) {
                    const demo = el("a", "portfolio-link portfolio-link-demo");
                    demo.href = demoUrl;
                    demo.target = "_blank";
                    demo.rel = "noopener noreferrer";
                    demo.appendChild(el("i", "fa fa-external-link"));
                    demo.appendChild(document.createTextNode(" Live Demo"));
                    links.appendChild(demo);
                }

                if (codeUrl) {
                    const code = el("a", "portfolio-link portfolio-link-code");
                    code.href = codeUrl;
                    code.target = "_blank";
                    code.rel = "noopener noreferrer";
                    code.appendChild(el("i", "fa fa-github"));
                    code.appendChild(document.createTextNode(" Code"));
                    links.appendChild(code);
                }

                footer.appendChild(links);
                content.appendChild(footer);
                inner.appendChild(content);

                const overlay = el("div", "portfolio-overlay");
                const overlayContent = el("div", "portfolio-overlay-content");
                overlayContent.appendChild(el("h4", null, repo.name));
                overlayContent.appendChild(el("p", null, demoUrl ? "Open live demo" : "View on GitHub"));
                overlay.appendChild(overlayContent);
                inner.appendChild(overlay);

                cardEl.appendChild(inner);
                item.appendChild(cardEl);

                // The whole card is clickable, but the real anchors inside it
                // handle their own clicks. Without the guard, clicking "Live
                // Demo" or "Code" opens the link and then bubbles up here,
                // which opens a second tab.
                //
                // Bound per card against the URL already validated above, so a
                // hostile homepage cannot reach window.open either.
                const target = demoUrl || codeUrl;
                if (target) {
                    cardEl.addEventListener("click", (event) => {
                        if (event.target.closest("a")) return;
                        window.open(target, "_blank", "noopener");
                    });
                }

                portfolioContainer.appendChild(item);
            });
```

- [ ] **Step 4: Delete the old click-handler block**

The `document.querySelectorAll('.portfolio-card').forEach((card, index) => { ... });` block that
followed the renderer is now redundant, and it was the second unvalidated `window.open` sink.
Delete it in full, including its leading comment about the anchor guard, which has moved into
the renderer above. The `catch`/`finally` block that follows is unchanged.

- [ ] **Step 5: Run the checks**

Run: `python3 tools/verify_security.py 2>&1 | grep -e interpolate -e safeUrl -e window.open -e href -e https`

Expected: PASS on all six `repo.*` interpolation checks, on `safeUrl`, on both sink checks, and
on `index.html names the https: scheme it allows`.

Run: `python3 tools/verify_security.py 2>&1 | grep -A3 "Inline scripts parse"`

Expected: `PASS  index.html inline script 1 parses`. A syntax error in the rewritten renderer
fails here rather than silently blanking the portfolio section in a browser.

Run: `python3 tools/verify_assets.py > /dev/null; echo "assets=$?"; python3 tools/verify_interactivity.py > /dev/null; echo "interactivity=$?"`

Expected: both 0. `verify_interactivity.py` asserts the card click handler yields to real
anchors; the `event.target.closest("a")` guard is preserved above.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "fix: build portfolio cards with DOM APIs and validate repo URLs"
```

---

### Task 4: Delete the mixed-content and IE8 references

Two deletions, one task: both are dead template leftovers in the same two files, and neither has
a test cycle a reviewer could separate from the other.

**Files:**
- Modify: `css/style.css:530-540` (three rules)
- Modify: `index.html:43-48` (the IE conditional block)

**Interfaces:**
- Consumes: Task 1's `check_no_plain_http_assets` and `check_no_ie_conditional_shims`.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Confirm the checks currently fail**

Run: `python3 tools/verify_security.py 2>&1 | grep -e http:// -e placehold -e "IE conditional" -e html5shiv -e respond -e maxcdn`

Expected: FAIL for `css/style.css has no http:// asset reference`, for
`css/style.css no longer references placehold.it`, and for all four IE checks.

- [ ] **Step 2: Delete the three placeholder rules**

Remove these three rules from `css/style.css` in full, including the blank lines between them.
`placehold.it` has been offline for years, these are `http://` on an https site, and no page has
a `.home-carousel` element.

```css
.home-carousel .first-slide {
    background-image: url(http://placehold.it/1200x800);
}

.home-carousel .second-slide {
    background-image: url(http://placehold.it/1200x800);
}

.home-carousel .third-slide {
    background-image: url(http://placehold.it/1200x800);
}
```

Leave every other `.home-carousel` and `.owl-*` rule alone. Unmatched selectors are harmless and
that cleanup is issue #18's scope.

- [ ] **Step 3: Delete the IE conditional block**

Remove these six lines from the `<head>` of `index.html`. MaxCDN's open-source CDN shut down, so
these two `src` values resolve to nothing; conditional comments have not been honored since IE10;
and IE itself is end of life.

```html
    <!-- HTML5 shim and Respond.js for IE8 support of HTML5 elements and media queries -->
    <!-- WARNING: Respond.js doesn't work if you view the page via file:// -->
    <!--[if lt IE 9]>
    <script src="https://oss.maxcdn.com/html5shiv/3.7.3/html5shiv.min.js"></script>
    <script src="https://oss.maxcdn.com/respond/1.4.2/respond.min.js"></script>
    <![endif]-->
```

- [ ] **Step 4: Run the checks**

Run: `python3 tools/verify_security.py 2>&1 | grep -e "http://" -e placehold -e "IE conditional" -e html5shiv -e respond -e maxcdn`

Expected: PASS on all four `http://` file checks, on the `placehold.it` check, and on all four IE
checks.

Run: `python3 tools/verify_assets.py > /dev/null; echo "assets=$?"; python3 tools/verify_interactivity.py > /dev/null; echo "interactivity=$?"`

Expected: both 0.

- [ ] **Step 5: Commit**

```bash
git add css/style.css index.html
git commit -m "fix: remove placehold.it mixed content and dead IE8 shims"
```

---

### Task 5: Unify Font Awesome on the local 4.7.0 build

**Files:**
- Modify: `resume.html:7` (stylesheet link), `resume.html:442` (redundant script),
  `resume.html:331-422` (11 icon classes)

**Interfaces:**
- Consumes: Task 1's `check_font_awesome_is_single_local_version`.
- Produces: nothing other tasks depend on. `index.html` is untouched; its 16 icons already use
  FA4 syntax against the local stylesheet.

- [ ] **Step 1: Confirm the checks currently fail**

Run: `python3 tools/verify_security.py 2>&1 | grep -e cdnjs -e "FA5/FA6" -e "font-awesome.min.css"`

Expected: FAIL for `resume.html loads no asset from cdnjs`, for
`resume.html uses no FA5/FA6 style class (fas, fab, far, fal)`, and for
`resume.html links the local css/font-awesome.min.css`.

- [ ] **Step 2: Swap the stylesheet link**

In `resume.html`, replace line 7:

```html
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
```

with:

```html
    <link rel="stylesheet" href="css/font-awesome.min.css">
```

- [ ] **Step 3: Delete the redundant Font Awesome script**

Remove the last `<script>` in `resume.html`, immediately before `</body>`:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/js/all.min.js" crossorigin="anonymous"></script>
```

Loading both the CSS and the JS build pulls the icon set twice for no benefit. The CSS build
alone renders `<i class="fa ...">` markup.

- [ ] **Step 4: Rewrite the 11 icon classes to FA4 syntax**

FA4 has no `fas`/`fab` style classes; the base class is a bare `fa`. Every replacement below was
confirmed present in `css/font-awesome.min.css` (4.7.0). Two names differ between the majors:
`fa-map-marker-alt` is `fa-map-marker` in FA4, and `fa-file-pdf` is `fa-file-pdf-o`.

| Line | From | To |
|---|---|---|
| 331 | `fas fa-envelope icon` | `fa fa-envelope icon` |
| 332 | `fas fa-phone icon` | `fa fa-phone icon` |
| 333 | `fab fa-linkedin icon` | `fa fa-linkedin icon` |
| 335 | `fab fa-github icon` | `fa fa-github icon` |
| 338 | `fas fa-map-marker-alt icon` | `fa fa-map-marker icon` |
| 344 | `fas fa-user icon` | `fa fa-user icon` |
| 353 | `fas fa-code icon` | `fa fa-code icon` |
| 364 | `fas fa-briefcase icon` | `fa fa-briefcase icon` |
| 401 | `fas fa-graduation-cap icon` | `fa fa-graduation-cap icon` |
| 410 | `fas fa-certificate icon` | `fa fa-certificate icon` |
| 422 | `fas fa-file-pdf` | `fa fa-file-pdf-o` |

The class attribute on line 422 is split across two source lines
(`<i\n            class="fas fa-file-pdf"></i>`). Match the existing wrapping when editing it.

- [ ] **Step 5: Run the checks**

Run: `python3 tools/verify_security.py 2>&1 | grep -e cdnjs -e "FA5/FA6" -e "font-awesome.min.css"`

Expected: PASS on all three `resume.html` checks and on the `index.html` and `privacy.html`
equivalents.

Confirm no FA6 class survived anywhere:

Run: `grep -n 'fa[sbrl] fa-' index.html resume.html privacy.html; echo "matches=$?"`

Expected: `matches=1` (grep found nothing).

Run: `python3 tools/verify_assets.py > /dev/null; echo "assets=$?"; python3 tools/verify_interactivity.py > /dev/null; echo "interactivity=$?"`

Expected: both 0.

- [ ] **Step 6: Commit**

```bash
git add resume.html
git commit -m "fix: serve Font Awesome once from the local 4.7.0 build"
```

---

### Task 6: Correct CLAUDE.md and green the full gate

**Files:**
- Modify: `CLAUDE.md:11-21` (Technology Stack), plus a Development Workflow entry for the new
  verifier

**Interfaces:**
- Consumes: every prior task.
- Produces: the final green state of all three verifiers.

- [ ] **Step 1: Confirm the check currently fails**

Run: `python3 tools/verify_security.py 2>&1 | grep "CLAUDE.md names"`

Expected: `FAIL  CLAUDE.md names the shipped jQuery version (3.7.1)`.

- [ ] **Step 2: Correct the version claim**

In the Technology Stack list, replace:

```markdown
  - jQuery 3.x (js/jquery.min.js)
  - Bootstrap JS (js/bootstrap.min.js)
```

with:

```markdown
  - jQuery 3.7.1 (js/jquery.min.js)
  - Bootstrap JS 3.3.7 (js/bootstrap.min.js)
```

Then add, after the existing paragraph about the libraries removed in issue #15:

```markdown
The file shipped jQuery 2.2.4 for two years while this document claimed 3.x, which left
CVE-2020-11022, CVE-2020-11023, and CVE-2019-11358 open (issue #17). It is now 3.7.1, and
`tools/verify_security.py` asserts the version in the file against the version named here, so
the claim cannot drift again. Bootstrap 3.3.7 is the release that added jQuery 3 support; do
not downgrade one without the other.

Font Awesome is 4.7.0, served locally from `css/font-awesome.min.css` and `fonts/`, on every
page. `resume.html` used to pull 6.5.1 from cdnjs, twice and without SRI, which meant two icon
majors, two syntaxes, and a third party on the critical path. Use bare `fa fa-*` classes; the
FA5/FA6 `fas`/`fab`/`far` style classes render nothing here and the verifier rejects them.
```

- [ ] **Step 3: Document the verifier**

In the Development Workflow section, after the "Verifying the asset budget" block, add:

```markdown
### Verifying the security criteria

```bash
python3 tools/verify_security.py
```

Exits 0 when the issue #17 acceptance criteria still hold: jQuery is at or above 3.5, the
version in the file matches the one named in this document, no GitHub API field is interpolated
into a template literal or an `href`, repo-supplied URLs pass `safeUrl()` before reaching an
`href` or `window.open`, no page or stylesheet requests an `http://` asset, no IE conditional
shim survives, and Font Awesome is one local major site-wide. Standard library only. Run it
after touching the portfolio renderer, any `<script>`/`<link>` tag, or a bundled library.

It also runs `node --check` over every inline `<script>` in `index.html` and `resume.html`, the
way `verify_interactivity.py` does for `js/main.js`. The portfolio renderer is about 90 lines of
inline JavaScript, and before this it had no syntax gate at all. `node` is a convenience, skipped
when absent, never a project dependency.
```

Also update the "Dynamic Portfolio Loading" section, which describes the old string-building
renderer, to say the cards are built with `document.createElement` and `textContent` and that
`safeUrl()` gates the demo and code links.

- [ ] **Step 4: Run the full gate**

Run each, in order:

```bash
python3 tools/verify_security.py; echo "security=$?"
python3 tools/verify_assets.py; echo "assets=$?"
python3 tools/verify_interactivity.py; echo "interactivity=$?"
```

Expected: `security=0`, `assets=0`, `interactivity=0`, and `All checks passed.` from the first
two.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: correct jQuery version claim and document the security verifier"
```

---

## Manual verification (Phase 6 live drive, not a task)

Source-level checks cannot prove the escaping holds at runtime. Drive these in a browser against
`python3 -m http.server 8010`, with the GitHub API response stubbed to a hostile payload:

1. **Happy path.** `http://localhost:8010/` renders portfolio cards with titles, languages, star
   counts, descriptions, and working "Live Demo" and "Code" anchors. Clicking the card body opens
   the demo; clicking an anchor opens exactly one tab.
2. **Injected markup.** Stub a repo with `name` of `<img src=x onerror="window.__pwned=1">` and a
   description containing `<script>window.__pwned=1</script>`. The card must show those strings
   as literal text, and `window.__pwned` must stay `undefined`.
3. **Hostile homepage.** Stub `homepage` of `javascript:window.__pwned=1`. No "Live Demo" anchor
   may render, and clicking the card body must open the repo's `html_url`, never execute the
   payload.
4. **Nav and skill bars unbroken under jQuery 3.7.1.** Sticky navbar past 100px, scroll-to-top
   past 1000px, smooth scroll to each section landing clear of the fixed header, active nav link
   tracking, mobile navbar collapse closing after a tap, and skill bars animating to their
   `data-percent` widths once the skills section scrolls into view.
5. **Resume icons.** `http://localhost:8010/resume.html` renders all 11 icons as glyphs, not
   empty boxes, in both light and dark mode. DevTools Network shows zero requests to
   `cdnjs.cloudflare.com`.
