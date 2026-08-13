#!/usr/bin/env python3
"""Check the portfolio data criteria from issue 20.

Run from the repository root:

    python3 tools/verify_portfolio.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.

Offline and deterministic by default, like the other five verifiers. The one
criterion that cannot be settled from the source, "every Live Demo link
resolves", is settled two ways: tools/build_projects.py probes every homepage
at generation time and omits the ones that do not answer, and this file
unit-tests that probing logic with an injected probe. Pass --check-links to
additionally probe the URLs that actually shipped in projects.json, which needs
the network and is therefore not part of the default gate.

The emoji scan below covers index.html and projects.json alone. resume.html
carries a moon and a sun glyph on its dark mode toggle at lines 368, 460, and
466. Those are visible UI on a page issue 20 does not mention, and swapping
them for Font Awesome glyphs is a design change this issue did not ask for.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
STYLE_CSS = ROOT / "css" / "style.css"
PROJECTS = ROOT / "projects.json"

# tools/ is already on sys.path when this file is run as a script, but not when
# it is imported, and `import build_projects` below is the whole point of four
# of the checks.
sys.path.insert(0, str(ROOT / "tools"))

# Codepoint ranges that carry pictographs, written as escapes rather than as
# literal characters: a range whose endpoints are invisible glyphs is a range
# nobody can review, and U+FE0F in particular is zero width. U+2605 BLACK STAR
# sits in Miscellaneous Symbols and is caught by the first range, which is the
# point: it was the last non-ASCII character in index.html.
EMOJI_RANGES = re.compile(
    "[\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]"
)

# Selectors the portfolio cards need. Asserting the CSS moved means asserting
# it arrived, not just that it left index.html.
MOVED_SELECTORS = [
    "#github-projects",
    ".portfolio-item",
    ".portfolio-card",
    ".portfolio-title",
    ".portfolio-description p",
    ".portfolio-stars",
    ".portfolio-language",
    ".portfolio-link-demo",
    ".portfolio-link-code",
    ".portfolio-overlay",
    ".portfolio-error",
]

PROBE_TIMEOUT = 15

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

    Same helper, and the same reason, as verify_assets.without_comments: a
    comment has to quote the thing it explains, and the comment in index.html
    saying why the renderer no longer calls api.github.com contains the string
    "api.github.com".
    """
    pattern = r"/\*.*?\*/" if style == "css" else r"<!--.*?-->"
    return re.sub(pattern, "", source, flags=re.S)


def load_projects():
    """The projects list from projects.json, or None if it cannot be read.

    Returning None rather than raising keeps a malformed file to the one FAIL
    line check_projects_json_is_well_formed already prints, instead of a
    traceback that kills every check after it.
    """
    raw = read(PROJECTS)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    projects = data.get("projects")
    return projects if isinstance(projects, list) else None


def import_generator():
    """tools/build_projects.py, or None after printing one FAIL line."""
    try:
        import build_projects
    except ImportError as error:
        fail("tools/build_projects.py is importable: %s" % error)
        return None
    return build_projects


def check_no_visitor_side_api_call():
    """Criterion 1. The section renders with no GitHub API call from a visitor.

    The old renderer called api.github.com once per account, three times per
    page load. The unauthenticated limit is 60 requests per hour per IP
    address, so roughly 20 loads from a shared address blanked the section.
    """
    print("\nThe page makes no GitHub API call")

    source = read_or_fail(INDEX)
    if source is None:
        return
    source = without_comments(source, "html")

    check(
        "api.github.com" not in source,
        "index.html does not call api.github.com",
    )
    check(
        "projects.json" in source,
        "index.html reads the generated projects.json instead",
    )


def check_projects_json_is_well_formed():
    """Criteria 1 and 5. The committed data is complete and every URL is https."""
    print("\nprojects.json is well formed")

    raw = read_or_fail(PROJECTS)
    if raw is None:
        return

    try:
        data = json.loads(raw)
    except ValueError as error:
        fail("projects.json is valid JSON (%s)" % error)
        return
    check(True, "projects.json parses")

    if not check(isinstance(data, dict), "projects.json holds an object"):
        return
    generated = data.get("generated")
    check(
        isinstance(generated, str) and generated.endswith("Z"),
        "projects.json records a UTC generation timestamp",
    )

    projects = data.get("projects")
    if not check(isinstance(projects, list), "projects.json holds a projects list"):
        return
    if not check(bool(projects), "projects.json is not empty"):
        return

    for index, project in enumerate(projects):
        label = "project %d" % index
        if not check(isinstance(project, dict), "%s is an object" % label):
            continue
        label = project.get("name") or label

        check(
            isinstance(project.get("name"), str) and project["name"].strip() != "",
            "%s names a repo" % label,
        )
        for field in ("description", "language"):
            check(
                isinstance(project.get(field), str),
                "%s has a string %s, never null" % (label, field),
            )
        check(
            isinstance(project.get("stars"), int) and project["stars"] >= 0,
            "%s has a non-negative star count" % label,
        )
        code = project.get("code")
        check(
            isinstance(code, str) and code.startswith("https://"),
            "%s links its code over https" % label,
        )
        demo = project.get("demo")
        check(
            demo is None or (isinstance(demo, str) and demo.startswith("https://")),
            "%s demo link is https or absent, never anything else" % label,
        )


def check_no_magic_word_in_descriptions():
    """Criterion 3. The control flag is out of the user-facing copy."""
    print("\nNo control flag leaks into a description")

    projects = load_projects()
    if projects is None:
        return

    # The flag was written as a trailing hashtag, "#portfolio". A description
    # may still use the ordinary word: "a portfolio of neighborhood maps" is
    # prose, not a control flag, and failing on it would push the copy around
    # to satisfy a checker.
    for project in projects:
        description = project.get("description", "")
        check(
            "#portfolio" not in description.lower(),
            "%s description carries no #portfolio flag" % project.get("name", "?"),
        )


def check_filter_reads_topics_not_descriptions():
    """Criterion 3, at the generator. Filtering is topic-based, proven by behavior.

    Asserting this against the generator's source text would pass the moment
    the word "topics" appeared anywhere in it. Calling the function is the
    only way to know what it actually selects.
    """
    print("\nThe generator filters on the portfolio topic")

    build_projects = import_generator()
    if build_projects is None:
        return

    tagged = {"name": "tagged", "topics": ["portfolio"], "archived": False,
              "description": "no flag here"}
    described = {"name": "described", "topics": [], "archived": False,
                 "description": "matches the old filter #portfolio"}
    archived = {"name": "archived", "topics": ["portfolio"], "archived": True,
                "description": ""}
    untopiced = {"name": "untopiced", "archived": False, "description": ""}

    selected = [r["name"] for r in
                build_projects.select_repos([tagged, described, archived, untopiced])]

    check("tagged" in selected, "a repo with the portfolio topic is selected")
    check(
        "described" not in selected,
        "a repo with the word in its description but no topic is rejected",
    )
    check("archived" not in selected, "an archived repo is rejected")
    check(
        "untopiced" not in selected,
        "a repo with no topics key at all is rejected without raising",
    )


def check_one_account_failure_does_not_blank_the_section():
    """Criterion 2. A failing account costs its own repos and nothing else."""
    print("\nOne failing account does not blank the section")

    build_projects = import_generator()
    if build_projects is None:
        return

    def fetcher(account):
        if account == "broken":
            raise RuntimeError("simulated 502")
        return [{"name": account + "-repo", "topics": ["portfolio"],
                 "archived": False, "description": ""}]

    repos, failed = build_projects.collect(["broken", "working"], fetcher)
    check(
        [r["name"] for r in repos] == ["working-repo"],
        "a working account still contributes when another one fails",
    )
    check(failed == ["broken"], "the failing account is reported by name")

    # Every account failing is a different situation: there is no partial
    # result to keep, and writing an empty projects.json would blank the
    # section far more thoroughly than the bug this criterion is about.
    try:
        build_projects.collect(["broken"], fetcher)
    except RuntimeError:
        check(True, "every account failing raises instead of returning nothing")
    else:
        fail("every account failing raises instead of returning nothing")


def check_dead_demo_links_are_dropped():
    """Criterion 5. A demo that does not answer never reaches the page."""
    print("\nA dead demo link is dropped at generation time")

    build_projects = import_generator()
    if build_projects is None:
        return

    live = build_projects.resolve_demo("https://example.com/", lambda url: True)
    dead = build_projects.resolve_demo("https://example.com/", lambda url: False)
    insecure = build_projects.resolve_demo("http://example.com/", lambda url: True)
    missing = build_projects.resolve_demo(None, lambda url: True)

    check(live == "https://example.com/", "a demo that answers is kept")
    check(dead is None, "a demo that does not answer is dropped")
    check(insecure is None, "a non-https homepage is dropped without probing")
    check(missing is None, "a repo with no homepage yields no demo link")


def check_portfolio_css_lives_in_the_stylesheet():
    """Criterion 6. The CSS is a stylesheet, not a string injected at runtime."""
    print("\nPortfolio CSS lives in css/style.css")

    markup = read_or_fail(INDEX)
    css = read_or_fail(STYLE_CSS)
    if markup is None or css is None:
        return
    markup = without_comments(markup, "html")

    check(
        "portfolioCSS" not in markup,
        "index.html no longer builds a CSS string in JavaScript",
    )
    check(
        "insertAdjacentHTML" not in markup,
        "index.html no longer injects markup at runtime",
    )
    for selector in MOVED_SELECTORS:
        check(
            re.search(r"(?m)^%s\s*\{" % re.escape(selector), css) is not None,
            "css/style.css styles %s" % selector,
        )


def check_no_emoji_in_the_homepage():
    """Criterion 7. No pictograph in any output the page produces.

    projects.json is scanned too, because a repo description is copy someone
    types into a text box on github.com and lands on this page verbatim.
    """
    print("\nNo emoji in index.html or projects.json")

    for path in (INDEX, PROJECTS):
        source = read(path)
        if source is None:
            # projects.json missing is reported by its own check; index.html
            # missing is reported by every other check in this file.
            continue
        hits = sorted(set(EMOJI_RANGES.findall(source)))
        check(
            not hits,
            "%s carries no emoji or pictograph (found %s)"
            % (
                path.relative_to(ROOT),
                ", ".join("U+%04X" % ord(c) for c in hits) or "none",
            ),
        )


def check_links_live():
    """Opt-in, network. Probe the demo URLs that actually shipped.

    Not part of the default gate: the other five verifiers are offline and
    deterministic, and a check that fails because someone's wifi dropped
    teaches people to ignore the gate.
    """
    print("\nEvery shipped demo link answers (live probe)")

    projects = load_projects()
    if projects is None:
        return

    probed = 0
    for project in projects:
        demo = project.get("demo")
        if not demo:
            continue
        probed += 1
        request = urllib.request.Request(
            demo, headers={"User-Agent": "verify_portfolio"}
        )
        try:
            with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except Exception as error:  # noqa: BLE001 - any failure is a dead link
            fail("%s demo %s did not answer: %s" % (project.get("name"), demo, error))
            continue
        check(status < 400, "%s demo answers %d" % (project.get("name"), status))

    if probed == 0:
        print("  skip  no project ships a demo link")


def main():
    check_no_visitor_side_api_call()
    check_projects_json_is_well_formed()
    check_no_magic_word_in_descriptions()
    check_filter_reads_topics_not_descriptions()
    check_one_account_failure_does_not_blank_the_section()
    check_dead_demo_links_are_dropped()
    check_portfolio_css_lives_in_the_stylesheet()
    check_no_emoji_in_the_homepage()
    if "--check-links" in sys.argv:
        check_links_live()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
