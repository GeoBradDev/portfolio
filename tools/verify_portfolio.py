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
carries a moon and a sun glyph on its dark mode toggle, in the button's markup
and in the script that relabels it. Those are visible UI on a page issue 20
does not mention, and swapping them for icons from the page's SVG sprite is a
design change this issue did not ask for.

check_grid_reserves_its_final_height is issue 40's. The loading placeholder
holds the grid's final height so a deep link below the portfolio lands where
it should once the cards arrive. It asserts the reservation and the card
layout read the same four custom properties, that the declared card count
matches projects.json, that #portfolio is out of scroll anchoring only while
the placeholder or a status row is showing, and that the generator warns on
drift. It does not compute a height and does not know the
column breakpoints are the right ones; the browser drive is the proof that the
reserved box and the rendered grid are the same height.
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
    comment has to quote the thing it explains, and a bare substring scan
    counts that explanation as the offense it documents.

    It strips HTML comments and CSS comments, and deliberately not JavaScript
    line comments. A `//`-stripping regex cannot tell `// note` from the `//`
    inside `https://example.com`, and getting that wrong deletes real code
    from the text being scanned, which turns a FAIL into a silent PASS. A
    false PASS in a verifier is worse than a false FAIL.

    The consequence is a live constraint on the inline script in index.html:
    a `//` comment there must not contain the literal strings this file scans
    for, "api.github.com", "portfolioCSS", or "insertAdjacentHTML". The
    comment explaining why the renderer no longer calls the API says "the
    GitHub API" rather than the hostname for exactly this reason.
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
        check(
            isinstance(project.get("pushed"), str) and project["pushed"].endswith("Z"),
            "%s records when it was last pushed to" % label,
        )

    # The file's order is the display order: the renderer appends cards in the
    # order it reads them and re-sorts nothing. Asserting it here is what makes
    # the ordering a property of the data rather than an accident of whichever
    # sequence the generator's requests happened to complete in.
    #
    # pushed rather than updated on purpose. updated_at bumps on any metadata
    # change, so editing seven descriptions flattens seven repos to the same
    # minute and destroys the order; pushed_at moves only on a real push.
    stamps = [p.get("pushed") for p in projects if isinstance(p, dict)]
    check(
        stamps == sorted(stamps, reverse=True),
        "projects are ordered by last push, newest first",
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


# The one formula the loading placeholder may carry, whitespace removed. Pinned
# exactly rather than "mentions all four variables", because a formula that
# names all four and multiplies where it should divide reserves the wrong
# height just as surely as a literal does. Changing the formula means changing
# this line, on purpose.
RESERVATION = (
    "calc(round(up,var(--portfolio-cards)/var(--portfolio-cols),1)"
    "*(var(--portfolio-card-height)+var(--portfolio-row-gap)))"
)

GRID_VARIABLES = (
    "--portfolio-cards",
    "--portfolio-cols",
    "--portfolio-card-height",
    "--portfolio-row-gap",
)

# The base declarations that size a card and an item, whitespace removed, on
# the top-level rule whose selector is exactly the key's. Pinned for the same
# reason as RESERVATION: "reads the variable" passes calc(50% / var(...)) and a
# padding that adds 10px above the row gap.
LAYOUT = {
    (".portfolio-card", "height"): "var(--portfolio-card-height)",
    (".portfolio-item", "flex"): "00calc(100%/var(--portfolio-cols))",
    (".portfolio-item", "max-width"): "calc(100%/var(--portfolio-cols))",
    (".portfolio-item", "padding"): "015pxvar(--portfolio-row-gap)15px",
}

# Properties that change the height a card, an item, or the placeholder takes
# in the grid. Any of them on those elements, other than the pinned ones, is a
# FAIL. Deliberately not every property: width on a card or color on an item
# changes no row height and is none of this check's business.
_HEIGHT = {"height", "min-height", "max-height", "box-sizing"}
_MARGIN = {"margin", "margin-top", "margin-bottom", "margin-block",
           "margin-block-start", "margin-block-end"}
_PADDING = {"padding", "padding-top", "padding-bottom", "padding-block",
            "padding-block-start", "padding-block-end"}
CARD_SIZING = _HEIGHT | _MARGIN
ITEM_SIZING = _HEIGHT | _MARGIN | _PADDING | {
    "flex", "flex-basis", "flex-grow", "flex-shrink",
    "width", "min-width", "max-width",
}
LOADING_SIZING = _HEIGHT | _MARGIN
GRID_GAPS = {"gap", "row-gap", "grid-gap", "grid-row-gap"}

# The one rule allowed to touch scroll anchoring. :has() scopes the exclusion
# to the moments the grid is not cards: while loading, and on the error and
# empty status rows that replace the placeholder. Once the cards render,
# #portfolio is an ordinary anchor candidate again. Commas inside :has() do not
# split the selector list, so this is one selector.
ANCHOR_SELECTOR = "#portfolio:has(.portfolio-loading, .portfolio-status)"


def bare(value):
    """value without a trailing !important, which changes no reserved height."""
    return re.sub(r"\s*!\s*important\s*$", "", value, flags=re.I)


def squash(value):
    """bare(value) with all whitespace removed, for pinned comparisons."""
    return "".join(bare(value).split())


def split_outside(text, separator):
    """Split text on separator wherever it is not inside quotes or parentheses.

    A declaration value can hold a semicolon or a comma inside url('...') or
    inside a function's arguments, and splitting there would cut it in half.
    """
    parts, current, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return parts


def css_rules(css):
    """Every declaration block in css as (context, selectors, declarations).

    context is the tuple of at-rule preludes the block sits inside, empty at
    the top level, so a copy of a rule nested in a media query is still seen
    and still distinguishable from the base rule. selectors is the prelude
    split on top-level commas. declarations is a list of (property, value)
    with the property lowercased and the value's whitespace collapsed.

    Comments must already be stripped. This is a brace walker, not a CSS
    parser: it is only as good as style.css is ordinary, which it is.
    """
    rules, stack, buf, quote = [], [], [], None
    for ch in css:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "{":
            if stack:
                stack[-1][1] = True
            stack.append(["".join(buf).strip(), False])
            buf = []
        elif ch == "}":
            if not stack:
                buf = []
                continue
            prelude, has_children = stack.pop()
            if not has_children:
                declarations = []
                for part in split_outside("".join(buf), ";"):
                    if ":" not in part:
                        continue
                    prop, value = part.split(":", 1)
                    # Custom properties are case-sensitive, so
                    # --Portfolio-Cards is a different property and must not
                    # be folded onto --portfolio-cards.
                    prop = prop.strip()
                    if not prop.startswith("--"):
                        prop = prop.lower()
                    declarations.append((prop, " ".join(value.split())))
                rules.append((
                    tuple(p for p, _ in stack),
                    [" ".join(s.split()) for s in split_outside(prelude, ",")],
                    declarations,
                ))
            buf = []
        elif ch == ";" and not stack:
            # A top-level statement such as @import ends here; without this
            # reset its text would be read as the next rule's selector.
            buf = []
        else:
            buf.append(ch)
    return rules


def subject_compound(selector):
    """The compound selector a complex selector actually styles."""
    return re.split(r"\s*[\s>+~]\s*", selector.strip())[-1]


def styles(selector, token):
    """True when selector's subject carries token and is not a pseudo-element.

    `.portfolio-loading::after` is the spinner, and its 20px height is not the
    placeholder's; `.portfolio-card:hover .portfolio-overlay` styles the
    overlay, not the card. Both have to be told apart from the element itself.
    """
    compound = subject_compound(selector)
    if re.search(r"::|:(before|after|first-line|first-letter)\b", compound):
        return False
    return re.search(re.escape(token) + r"(?![\w-])", compound) is not None


def check_grid_reserves_its_final_height():
    """Issue 40. The loading placeholder holds the height the cards will take.

    projects.json arrives after the browser has already scrolled a deep link
    such as /#contact into place. If the placeholder is a one-line spinner and
    the cards then push #contact a whole grid further down, the visitor lands
    in the middle of the portfolio instead of at the form. The placeholder
    therefore carries the grid's final height, computed in CSS from four custom
    properties on #github-projects that the card layout reads too, and while
    the placeholder or a status row is showing, #portfolio is excluded from
    scroll anchoring so a browser that anchors picks the section below it.

    What this does not do: compute a height, or know that the two column
    breakpoints are the right ones. It proves the reservation and the layout
    read the same numbers and that the card count matches the data. That the
    reserved box and the rendered grid are the same height on screen is
    proven in a browser, at every breakpoint width, and nowhere else.
    """
    print("\nThe portfolio grid reserves its final height while loading")

    css = read_or_fail(STYLE_CSS)
    markup = read_or_fail(INDEX)
    projects = load_projects()
    if css is None or markup is None:
        return
    rules = css_rules(without_comments(css, "css"))

    def declared_on(subject, props):
        """(context, selectors, property, value) for every rule styling subject."""
        return [
            (ctx, sels, prop, v)
            for ctx, sels, decls in rules
            if any(styles(s, subject) for s in sels)
            for prop, v in decls
            if prop in props
        ]

    def show(found):
        return ["%s%s { %s: %s }" % ("".join("@%s " % c.lstrip("@") for c in ctx),
                                      ", ".join(sels), p, v)
                for ctx, sels, p, v in found] or "none"

    # 1. The four grid variables live on #github-projects and nowhere else, and
    # the card count is declared once and matches the data.
    variables = [
        (ctx, sels, prop, v)
        for ctx, sels, decls in rules
        for prop, v in decls
        if prop in GRID_VARIABLES
    ]
    elsewhere = [d for d in variables if d[1] != ["#github-projects"]]
    check(
        not elsewhere,
        "the grid variables are set only on #github-projects (strays: %s); a "
        "copy on a card, an item, or the placeholder gives that element its own "
        "column count or height, and the reserved space no longer matches the "
        "grid the visitor sees" % show(elsewhere),
    )
    counts = [d for d in variables if d[2] == "--portfolio-cards"]
    check(
        len(counts) == 1 and not counts[0][0],
        "--portfolio-cards is set once, on the top-level #github-projects rule "
        "(found %s); a second copy, or one only inside a media query, reserves "
        "a different number of rows than the data fills at some widths"
        % show(counts),
    )
    value = bare(counts[0][3]) if len(counts) == 1 else None
    declared = int(value) if value is not None and re.fullmatch(r"\d+", value) else None
    check(
        declared is not None,
        "--portfolio-cards is a bare integer (found %r); a unit or a decimal "
        "makes the reservation invalid, it collapses to one line, and in a "
        "browser without scroll anchoring (Safari) a deep link below the "
        "portfolio lands off by the whole grid" % value,
    )
    if projects is None:
        fail("projects.json can be read to count the cards; without it nobody "
             "can tell whether the reserved space fits the grid")
    else:
        check(
            declared == len(projects),
            "--portfolio-cards in css/style.css is %s and projects.json has %d "
            "cards; update the stylesheet after regenerating, or, in a browser "
            "without scroll anchoring (Safari), deep links below the portfolio "
            "land off by the change in rows"
            % ("missing" if declared is None else declared, len(projects)),
        )
    for name in GRID_VARIABLES[1:]:
        check(
            any(d[2] == name and not d[0] for d in variables),
            "%s has a base value on the top-level #github-projects rule; "
            "without one the reservation and the card layout are invalid at "
            "the widths no media query covers, and the placeholder collapses"
            % name,
        )

    # 2. The placeholder carries the formula, and nothing else sizes it.
    loading = declared_on(".portfolio-loading", LOADING_SIZING)
    reserving = [d for d in loading
                 if not d[0] and d[1] == [".portfolio-loading"]
                 and d[2] == "min-height" and squash(d[3]) == RESERVATION]
    others = [d for d in loading if d not in reserving]
    check(
        len(reserving) == 1,
        "the top-level .portfolio-loading rule's min-height is the grid's final "
        "height, computed from the four grid variables; without it the "
        "placeholder is one line tall and, in a browser without scroll "
        "anchoring (Safari), the cards push a deep-linked section down by the "
        "whole grid",
    )
    check(
        not others,
        "nothing else sizes .portfolio-loading (found %s); an extra height, "
        "margin, or box-sizing makes the placeholder a different height from "
        "the grid that replaces it" % show(others),
    )

    # 3. The layout reads the same variables the reservation does, through
    # exactly the declarations pinned in LAYOUT, and nothing else sizes a card,
    # an item, or the gaps between them.
    for subject, props in ((".portfolio-card", CARD_SIZING),
                           (".portfolio-item", ITEM_SIZING)):
        found = declared_on(subject, props)
        pinned = [d for d in found
                  if not d[0] and d[1] == [subject]
                  and squash(d[3]) == LAYOUT.get((subject, d[2]))]
        stray = [d for d in found if d not in pinned]
        missing = [p for (s, p) in LAYOUT if s == subject
                   and not any(d[2] == p for d in pinned)]
        check(
            not missing and not stray,
            "%s is sized only by its pinned declarations (missing: %s; strays: "
            "%s); any other height, width, column share, padding, or margin "
            "lays the cards out taller, shorter, or in a different number of "
            "rows than the space held for them"
            % (subject, ", ".join(missing) or "none", show(stray)),
        )
    gaps = declared_on("#github-projects", GRID_GAPS)
    check(
        not gaps,
        "#github-projects sets no gap of its own (found %s); a gap adds space "
        "between rows that the reservation does not count" % show(gaps),
    )

    # 4. #portfolio leaves scroll anchoring only while the placeholder or a
    # status row is showing. A permanent exclusion, or one anywhere else, takes
    # the anchor away from a visitor reading the cards: anything that changes
    # height above the section then moves the card they are reading.
    anchors = [
        (ctx, sels, prop, v)
        for ctx, sels, decls in rules
        for prop, v in decls
        if prop == "overflow-anchor"
    ]
    sanctioned = [d for d in anchors
                  if not d[0] and d[1] == [ANCHOR_SELECTOR] and bare(d[3]) == "none"]
    check(
        len(sanctioned) == 1 and len(anchors) == 1,
        "the only overflow-anchor in css/style.css is none on %s (found %s); "
        "without it an error or empty state moves a deep link by the collapsed "
        "reservation, and with any other one a visitor reading the cards is "
        "moved whenever something above the portfolio changes height"
        % (ANCHOR_SELECTOR, show(anchors)),
    )

    # 5. The renderer still starts the grid with the placeholder. A full-line
    # // comment cannot hold the //  of a URL, so dropping those is safe here.
    script = re.sub(r"(?m)^\s*//.*$", "", without_comments(markup, "html"))
    calls = list(re.finditer(r"(?m)^\s*(?:void\s+)?loadPortfolio\(\)\s*;?\s*$", script))
    call = calls[-1].start() if calls else -1
    writes = list(re.finditer(
        r"portfolioContainer\.innerHTML\s*=\s*(['\"`])(.*?)\1;",
        script[:call] if call != -1 else "",
    ))
    first = writes[-1].group(2) if writes else ""
    check(
        call != -1 and re.match(
            r"<div class=(['\"])([^'\"]*\s)?portfolio-loading(\s[^'\"]*)?\1", first
        ) is not None,
        "the renderer writes a .portfolio-loading element as the grid's initial "
        "content (found %r); without it nothing holds the space while loading "
        "and, in a browser without scroll anchoring (Safari), the cards push a "
        "deep-linked section down" % first[:60],
    )

    # 6. The generator warns when the count it writes drifts from the CSS.
    build_projects = import_generator()
    if build_projects is None:
        return
    warning_of = getattr(build_projects, "stylesheet_card_count_warning", None)
    if not check(
        callable(warning_of),
        "tools/build_projects.py defines stylesheet_card_count_warning",
    ):
        return
    sheet = "#github-projects {\n    --portfolio-cards: 7;\n}\n"
    check(
        warning_of(7, sheet) is None,
        "the generator stays quiet when the count matches; a false warning "
        "trains whoever regenerates to ignore the one that matters",
    )
    check(
        warning_of(7, sheet.replace(": 7;", ": 07;")) is None,
        "the generator reads --portfolio-cards: 07 as 7, like the gate and the "
        "browser do, instead of asking for a change that changes nothing",
    )
    drifted = warning_of(8, sheet)
    check(
        isinstance(drifted, str) and "--portfolio-cards: 8" in drifted
        and "css/style.css" in drifted,
        "the generator's drift warning names css/style.css and the exact "
        "--portfolio-cards: 8 line to write (got %r); without the line, whoever "
        "regenerates cannot fix the reservation the visitor depends on" % drifted,
    )
    commented = "/* --portfolio-cards: 7; */\n#github-projects {}\n"
    check(
        isinstance(warning_of(7, commented), str),
        "the generator warns when the only declaration is inside a comment, "
        "which the browser ignores, leaving the placeholder one line tall",
    )
    check(
        isinstance(warning_of(7, "#github-projects {}\n"), str),
        "the generator warns when the stylesheet declares no count, which "
        "leaves the placeholder one line tall",
    )
    check(
        isinstance(warning_of(7, sheet + "@media (max-width: 1px) {\n"
                              "    #github-projects { --portfolio-cards: 7; }\n}\n"),
                   str),
        "the generator warns when the stylesheet declares the count twice, "
        "which reserves different heights at different widths",
    )
    check_generator_main_warns(build_projects)


def check_generator_main_warns(build_projects):
    """Run the generator's real main() offline and read what it prints.

    Proves the wiring, which calling the helper alone cannot: main() has to
    call it with the count it actually wrote, print the warning, and leave the
    stylesheet untouched. Every network and filesystem seam is swapped for a
    temporary stand-in and restored afterward.
    """
    import contextlib
    import io
    import tempfile

    if not check(
        hasattr(build_projects, "STYLESHEET"),
        "tools/build_projects.py names the stylesheet it reads as STYLESHEET; "
        "without it the gate cannot prove the generator warns before a stale "
        "count reaches visitors",
    ):
        return
    repo = {"name": "only", "topics": ["portfolio"], "archived": False,
            "description": "", "owner": {"login": build_projects.ACCOUNTS[0]},
            "html_url": "https://github.com/x/only", "homepage": None,
            "pushed_at": "2026-01-01T00:00:00Z"}
    saved = {name: getattr(build_projects, name)
             for name in ("fetch_repos", "probe", "OUTPUT", "STYLESHEET")}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            build_projects.fetch_repos = lambda account: [repo] if account == build_projects.ACCOUNTS[0] else []
            build_projects.probe = lambda url: False
            build_projects.OUTPUT = Path(tmp) / "projects.json"
            build_projects.STYLESHEET = Path(tmp) / "style.css"
            for declared, expect_warning in ((7, True), (1, False)):
                sheet = "#github-projects {\n    --portfolio-cards: %d;\n}\n" % declared
                build_projects.STYLESHEET.write_text(sheet, encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    status = build_projects.main()
                warned = "--portfolio-cards: 1" in err.getvalue()
                check(
                    status == 0 and warned == expect_warning,
                    "the generator's main() %s when the stylesheet says %d and "
                    "it writes 1 card; %s"
                    % ("warns" if expect_warning else "stays quiet", declared,
                       "otherwise a stale count reaches visitors unannounced"
                       if expect_warning else "otherwise its warnings are noise"),
                )
                check(
                    build_projects.STYLESHEET.read_text(encoding="utf-8") == sheet,
                    "the generator never writes the stylesheet; a data script "
                    "editing hand-authored CSS can silently overwrite a fix",
                )
    finally:
        for name, value in saved.items():
            setattr(build_projects, name, value)


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
    check_grid_reserves_its_final_height()
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
