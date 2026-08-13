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

# Every page at the repo root, discovered once from the filesystem instead of
# hardcoded per check. check_no_plain_http_assets and
# check_font_awesome_is_single_local_version used to each list the pages by
# hand, which meant a page added after those lists were written was silently
# exempt from both scans. The named constants above stay, for the checks that
# mean one specific file by name rather than "every page".
HTML_PAGES = sorted(ROOT.glob("*.html"))

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
    """Return path's text, or None if the file does not exist.

    A file this script scans can be renamed or deleted without this script
    changing. Returning None instead of letting read_text() raise means the
    caller decides how to report that, instead of the whole run dying with a
    traceback partway through and every remaining check silently never
    running.
    """
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def read_or_fail(path):
    """read(), plus turning a missing file into one FAIL line instead of None."""
    text = read(path)
    check(text is not None, "%s exists" % path.relative_to(ROOT))
    return text


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
    doc = read_or_fail(CLAUDE_MD)
    if doc is None:
        return
    check(
        version in doc,
        "CLAUDE.md names the shipped jQuery version (%s)" % version,
    )


def check_no_unescaped_interpolation():
    print("\nNo remote GitHub data reaches innerHTML")

    source = read_or_fail(INDEX)
    if source is None:
        return

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

    # The per-field match above only catches the literal text "repo.<field>".
    # One alias defeats it: `const name = repo.name;` and then `${name}` in a
    # template literal carries the same remote data past every check above
    # without the string "repo.name" appearing anywhere near the sink. The
    # pattern below is a backstop for exactly that one shape, not a general
    # XSS gate: a backtick template literal written literally at an
    # innerHTML/outerHTML assignment, or at an insertAdjacentHTML call site,
    # containing any interpolation at all. The actual defense against
    # unescaped remote data is that the renderer builds DOM nodes and sets
    # textContent instead of assigning HTML strings; this regex only guards
    # against someone regressing to string assignment with the alias trick
    # above still open.
    #
    # Bypasses that stay invisible to this pattern, each driven through this
    # exact check by hand with an aliased repo field: the template literal
    # assigned to a variable before it reaches the sink (const html =
    # `...${a}...`; el.innerHTML = html;); String.raw and other tagged
    # templates; string concatenation with + instead of interpolation;
    # innerHTML +=; document.write; insertAdjacentHTML reached through an
    # alias or .bind; range.createContextualFragment; jQuery's .html() and
    # .append() (jQuery 3.7.1 is loaded on index.html); and
    # Element.setHTMLUnsafe. Any of these carries remote data past this
    # check untouched.
    #
    # It also has a false positive: it flags any interpolation at these
    # sinks, escaped or not. `${escapeHtml(repo.name)}` fails this check
    # exactly like `${repo.name}` does, and so does `${n}` for a plain
    # number n. Today's tree is unaffected only because the renderer builds
    # DOM nodes instead of assigning HTML strings at the sinks below; a
    # future change that assigns an escaped template literal here will FAIL,
    # and this pattern would need to allow-list the escaping call before
    # that becomes legal.
    #
    # index.html has two template-literal HTML sinks today. The error-path
    # innerHTML assignment is a literal string with no interpolation. The
    # portfolioCSS block reaches insertAdjacentHTML through a variable
    # reference, not as a literal at the call site, so this pattern never
    # even sees it; it also contains no ${ of its own (checked by hand: it
    # is pure CSS, no repo data). Neither trips this check; a repo.name
    # alias would.
    sink_pattern = re.compile(
        r"\.(?:innerHTML|outerHTML)\s*=\s*`(?P<assign>.*?)`"
        r"|insertAdjacentHTML\([^)]*?,\s*`(?P<call>.*?)`",
        re.S,
    )
    offenders = [
        match.group("assign") or match.group("call")
        for match in sink_pattern.finditer(source)
        if "${" in (match.group("assign") or match.group("call"))
    ]
    check(
        not offenders,
        "index.html has no innerHTML/outerHTML/insertAdjacentHTML sink fed by a template interpolation",
    )

    check(
        "safeUrl" in source,
        "index.html defines a safeUrl helper for repo-supplied URLs",
    )


def check_repo_urls_are_scheme_validated():
    print("\nRepo-supplied URLs are scheme validated before use")

    source = read_or_fail(INDEX)
    if source is None:
        return

    # Both navigable sinks: the anchor href and the whole-card window.open.
    check(
        re.search(r"window\.open\(\s*repo\.", source) is None,
        "index.html does not pass a raw repo field to window.open",
    )
    check(
        re.search(r"href\s*=\s*repo\.", source) is None,
        "index.html does not assign a raw repo field to an href",
    )

    # href = repo.<field> only catches direct property assignment.
    # setAttribute('href', repo.homepage) reaches the same sink through a
    # call the text check above never sees, so it needs its own pattern.
    check(
        re.search(r"setAttribute\(\s*['\"](?:href|src)['\"]\s*,\s*repo\.", source) is None,
        "index.html does not setAttribute an href/src from a raw repo field",
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

    # HTML_PAGES is discovered from the filesystem, not hardcoded, so a page
    # added after this check was written is scanned automatically.
    style_source = None
    for path in [STYLE_CSS] + HTML_PAGES:
        source = read_or_fail(path)
        if path == STYLE_CSS:
            style_source = source
        if source is None:
            continue
        hits = asset_http.findall(source)
        check(
            not hits,
            "%s has no http:// asset reference" % path.relative_to(ROOT),
        )

    if style_source is not None:
        check(
            "placehold.it" not in style_source,
            "css/style.css no longer references placehold.it",
        )


def check_no_ie_conditional_shims():
    print("\nNo IE conditional comment shims")

    source = read_or_fail(INDEX)
    if source is None:
        return
    check("[if lt IE" not in source, "index.html has no IE conditional comment")
    check("html5shiv" not in source, "index.html does not load html5shiv")
    check("respond.min.js" not in source, "index.html does not load Respond.js")
    check("maxcdn.com" not in source, "index.html does not reference the dead MaxCDN host")


def check_font_awesome_is_single_local_version():
    print("\nFont Awesome is one local version site-wide")

    # HTML_PAGES is discovered from the filesystem, not hardcoded, so a page
    # added after this check was written is scanned automatically.
    pages = {}
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        pages[path.name] = source

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
        source = pages.get(name)
        if source is None or "fa-" not in source:
            continue
        check(
            "css/font-awesome.min.css" in source,
            "%s links the local css/font-awesome.min.css" % name,
        )


def check_inline_script_syntax():
    """The portfolio renderer lives inline, where node --check cannot see it.

    verify_interactivity.py syntax-checks js/main.js, but the ~90 lines that
    build the portfolio cards sit in an inline <script> in index.html and had
    no gate at all. Extract every inline <script> block, meaning any script
    tag without a src attribute regardless of what other attributes it
    carries, and check it. node is a convenience here, never a project
    dependency.
    """
    print("\nInline scripts parse")

    if shutil.which("node") is None:
        print("  skip  node not found, cannot syntax-check inline scripts")
        return

    # <script\s*> only matched an attribute-less tag, so <script type="module">
    # or <script defer> got no gate at all, and silently: a plain <script>
    # block elsewhere in the same file already satisfied the "has an inline
    # script to check" assertion below. Match any script tag without a src
    # attribute instead; a tag WITH src loads external code that this check
    # is not meant to see.
    inline = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S)

    # Iterating (INDEX, RESUME) exempted any page added later, which is the
    # same silent-exemption bug the HTML_PAGES glob was introduced to fix for
    # the other checks. Sweep every discovered page instead.
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        blocks = inline.findall(source)
        name = path.relative_to(ROOT)

        # index.html and resume.html are expected to carry inline script, so
        # finding none there means the extraction pattern broke rather than
        # that the script is gone. A page that legitimately has none,
        # thanks.html or the Termly privacy paste, must not fail for that.
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
