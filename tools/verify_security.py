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
