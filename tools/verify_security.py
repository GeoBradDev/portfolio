#!/usr/bin/env python3
"""Check the dependency and security criteria from issue 17.

Run from the repository root:

    python3 tools/verify_security.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.

Source-level only. That the escaped card actually renders, and that a hostile
homepage URL is actually refused at runtime, has to be driven in a browser.

Issue 35 added one check that is not about issue 17: check_ci_workflow asserts
that .github/workflows/verify.yml still gates merges. Inside the job with id
`verify`, which has no name: override, every tools/verify_*.py on disk runs
once, as a bare `run: python3 tools/verify_x.py` line under
`if: ${{ !cancelled() }}` or `if: ${{ always() }}`, with no shell: override;
the job has no if:, needs:, strategy:, container:, services:, or defaults:,
and neither does the file at top level (defaults:); checkout, setup-python,
and setup-node are the only actions, each pinned and unconditional, and
checkout does not persist credentials. Nowhere in
the file is there a write permission, a secret or token, continue-on-error,
--check-links, an install or fetch, or pull_request_target, and the triggers
are a pull_request with no paths, types, or branches-ignore filter (and a
branches: list, if any, that includes main) plus a push to main. Branch protection requires
the check named `verify`, so a renamed job, a dropped verifier, a seventh one
nobody wired in, or a step that cannot fail would otherwise stop gating
merges with nothing failing. It reads the file line by line with regexes,
standard library only, so it expects ordinary block style: two-space indents,
`on:`, `permissions:`, and `jobs:` as top-level keys, and block mappings under
them. It fails closed on anything else, such as flow-style triggers, a
quoted job id, or a zero-indented sequence (`steps:` with `- name:` at the
same indent), rather than guessing.

Issue 31 retired jQuery, Bootstrap, and Font Awesome and changed three checks.
check_no_end_of_life_library replaced the jQuery version floor: every script a
page loads is under js/, every stylesheet (and every as=style preload) is
under css/ or from Google Fonts, and nothing names a retired library.
check_css_imports_are_first_party holds the same line inside the
stylesheets, for @import and url(). check_icons_are_inline_svg replaced the
single-Font-Awesome-version check: no Font Awesome stylesheet or class
anywhere, and every icon a page or the portfolio renderer draws resolves to a
<symbol> on that page. Markup is read with html.parser, so attribute quoting
and rel token order cannot hide a tag.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
RESUME = ROOT / "resume.html"
PRIVACY = ROOT / "privacy.html"
STYLE_CSS = ROOT / "css" / "style.css"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
TOOLS = ROOT / "tools"

# Every page at the repo root, discovered once from the filesystem instead of
# hardcoded per check. check_no_plain_http_assets and the Font Awesome check
# that check_icons_are_inline_svg replaced used to each list the pages by
# hand, which meant a page added after those lists were written was silently
# exempt from both scans. The named constants above stay, for the checks that
# mean one specific file by name rather than "every page".
HTML_PAGES = sorted(ROOT.glob("*.html"))

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


# The libraries issue 31 retired: jQuery 3.x, Bootstrap 3.x (with its
# Glyphicons font), and Font Awesome 4.x. All are end of life, and jQuery
# stayed on 3.x only because Bootstrap 3 could not run on 4. A src, href, or
# url() naming any of them is one coming back.
RETIRED_LIBRARIES = re.compile(r"jquery|bootstrap|font-?awesome|glyphicons?", re.I)

# The only third-party origins a stylesheet may come from. Google Fonts serves
# a font, not a runtime library: the CSS from fonts.googleapis.com and the font
# files that CSS names from fonts.gstatic.com.
STYLESHEET_HOSTS = ("https://fonts.googleapis.com/",)
FONT_FILE_HOSTS = ("https://fonts.googleapis.com/", "https://fonts.gstatic.com/")

# A first-party path: relative, or root-absolute, with no scheme and no
# protocol-relative // host.
FIRST_PARTY_SCRIPT = re.compile(r"/?js/[\w./-]+\.js")
FIRST_PARTY_SHEET = re.compile(r"/?css/[\w./-]+\.css")


class PageAssets(HTMLParser):
    """What a page loads and draws, read by a real parser.

    The regexes this replaced matched only double-quoted attributes and an
    exact rel="stylesheet", so src='...', rel=stylesheet, rel="preload
    stylesheet", and an as=style preload all walked past them. html.parser
    hands back attribute values whatever their quoting, and rel is read as
    the space-separated token list it is.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []      # src of every <script src>
        self.sheets = []       # href of every stylesheet link or style preload
        self.preloads = []     # (as, href) of every other preload
        self.styles = []       # body of every inline <style>
        self.uses = []         # fragment of every <use href> or xlink:href
        self.symbols = set()   # id of every <symbol>
        self.classes = []      # every class token
        self.links = []        # href of every <link>, whatever its rel
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or "") for key, value in attrs}
        self.classes.extend(attr.get("class", "").split())
        if tag == "script" and "src" in attr:
            self.scripts.append(attr["src"].strip())
        elif tag == "link":
            rel = attr.get("rel", "").lower().split()
            href = attr.get("href", "").strip()
            self.links.append(href)
            kind = attr.get("as", "").strip().lower()
            if "stylesheet" in rel or ({"preload", "prefetch"} & set(rel) and kind == "style"):
                self.sheets.append(href)
            elif {"preload", "modulepreload", "prefetch"} & set(rel):
                self.preloads.append((kind, href))
        elif tag == "style":
            self._in_style = True
            self.styles.append("")
        elif tag == "use":
            href = attr.get("href") or attr.get("xlink:href") or ""
            self.uses.append(href.strip())
        elif tag == "symbol" and attr.get("id"):
            self.symbols.add(attr["id"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "style":
            self._in_style = False

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles[-1] += data


def page_assets(source):
    parser = PageAssets()
    parser.feed(_without_html_comments(source))
    parser.close()
    return parser


def check_no_end_of_life_library():
    """Every script and stylesheet a page loads is first-party, and none is retired.

    Replaces check_jquery_version, which asserted jQuery at or above 3.5 and
    cross-checked the version against CLAUDE.md. Issue 31 removed jQuery,
    Bootstrap, and Font Awesome, so there is no version left to floor or to
    document. What keeps a library from coming back unnoticed is now an
    allowlist: a <script src> must be a path under js/, a stylesheet (a link
    whose rel includes stylesheet, or a preload with as=style) must be under
    css/ or come from Google Fonts, a script preload must be under js/, and
    no src or href may name one of the retired libraries, wherever it is
    hosted.
    """
    print("\nNo page loads a third-party or end-of-life library")

    # HTML_PAGES is discovered from the filesystem, not hardcoded, so a page
    # added after this check was written is scanned automatically.
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        name = path.name
        assets = page_assets(source)

        scripts = assets.scripts + [href for kind, href in assets.preloads if kind == "script"]
        foreign = [src for src in scripts if not FIRST_PARTY_SCRIPT.fullmatch(src)]
        check(
            not foreign,
            "%s loads scripts only from js/%s"
            % (name, " (not: %s)" % ", ".join(foreign) if foreign else ""),
        )

        foreign = [
            href for href in assets.sheets
            if not FIRST_PARTY_SHEET.fullmatch(href) and not href.startswith(STYLESHEET_HOSTS)
        ]
        check(
            not foreign,
            "%s links stylesheets only from css/ or Google Fonts%s"
            % (name, " (not: %s)" % ", ".join(foreign) if foreign else ""),
        )

        everything = scripts + assets.sheets + [href for _, href in assets.preloads]
        retired = [ref for ref in everything if RETIRED_LIBRARIES.search(ref)]
        check(
            not retired,
            "%s loads no jQuery, Bootstrap, Glyphicons, or Font Awesome%s"
            % (name, " (loads %s)" % ", ".join(retired) if retired else ""),
        )


def _css_imports_and_urls(css):
    """(every @import target, every url() value) in a stylesheet, comments out.

    url() is read quote-aware, so the card grain's data: SVG, which carries
    url(%23grain) inside its own quoted value, is one value and not two.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    value = r"""url\(\s*(?:(['"])(.*?)\1|([^'")\s]*))\s*\)|(['"])(.*?)\4"""
    imports = []
    for match in re.finditer(r"@import\s+(?:" + value + r")", css, re.S | re.I):
        imports.append(match.group(2) or match.group(3) or match.group(5) or "")
    urls = []
    for match in re.finditer(r"""url\(\s*(?:(['"])(.*?)\1|([^'")\s]*))\s*\)""", css, re.S | re.I):
        urls.append((match.group(2) if match.group(1) else match.group(3)) or "")
    return imports, urls


def check_css_imports_are_first_party():
    """A stylesheet cannot pull in what the pages may not link.

    check_no_end_of_life_library reads the markup, and an @import at the top
    of css/style.css loads Bootstrap from a CDN without any page changing.
    So every stylesheet a page uses, its linked local files and its inline
    <style> blocks, may @import only from Google Fonts, and every url() in
    them is first-party, a data: URI (the portfolio grain is one), or a
    Google Fonts host, and names no retired library.
    """
    print("\nStylesheets import nothing third-party and name no retired library")

    sheets = {}
    for path in HTML_PAGES:
        source = read(path)
        if source is None:
            continue
        assets = page_assets(source)
        for number, body in enumerate(assets.styles, start=1):
            sheets["%s inline <style> %d" % (path.name, number)] = body
        for href in assets.sheets:
            if FIRST_PARTY_SHEET.fullmatch(href):
                local = ROOT / href.lstrip("/")
                text = read(local)
                if text is not None:
                    sheets[href.lstrip("/")] = text
    text = read(STYLE_CSS)
    if check(text is not None, "css/style.css exists"):
        sheets["css/style.css"] = text

    for label, css in sorted(sheets.items()):
        imports, urls = _css_imports_and_urls(css)
        bad_imports = [ref for ref in imports if not ref.startswith(STYLESHEET_HOSTS)]
        check(
            not bad_imports,
            "%s imports only from Google Fonts%s"
            % (label, " (imports %s)" % ", ".join(bad_imports) if bad_imports else ""),
        )
        foreign = []
        for ref in urls:
            if ref.startswith("data:"):
                continue
            third_party = re.match(r"[a-z][a-z0-9+.-]*:|//", ref, re.I) is not None
            if (third_party and not ref.startswith(FONT_FILE_HOSTS)) or RETIRED_LIBRARIES.search(ref):
                foreign.append(ref)
        check(
            not foreign,
            "%s has no third-party or retired-library url()%s"
            % (label, " (found %s)" % ", ".join(foreign) if foreign else ""),
        )


def check_no_unescaped_interpolation():
    print("\nNo remote GitHub data reaches innerHTML")

    source = read_or_fail(INDEX)
    if source is None:
        return

    # Every field the card renderer reads off a projects.json entry. The data
    # still originates on github.com, where a repo name and description are
    # whatever their owner typed, so it is still remote data by any measure
    # that matters here.
    #
    # Issue 20 renamed the fields, not the loop variable: homepage, html_url,
    # and stargazers_count became demo, code, and stars when the renderer
    # stopped calling the API directly. Leaving the old names here would have
    # left three of these six assertions matching nothing and passing
    # vacuously. The variable is still `repo`, which is what keeps the three
    # sink checks in check_repo_urls_are_scheme_validated matching.
    remote_fields = [
        "repo.name",
        "repo.description",
        "repo.demo",
        "repo.code",
        "repo.language",
        "repo.stars",
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
    # alias or .bind; range.createContextualFragment; and
    # Element.setHTMLUnsafe. Any of these carries remote data past this
    # check untouched. Since issue 31 no DOM library is loaded on any page,
    # so the native sinks listed here are the only ones there are; a
    # library's own HTML-string methods would be another way past.
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
    # index.html has two template-literal HTML sinks today, both innerHTML
    # assignments on the portfolio container and both literal strings with no
    # interpolation: the error path and the empty state. Neither trips this
    # check; a repo.name alias at either would.
    #
    # There used to be a third. The portfolioCSS block reached
    # insertAdjacentHTML through a variable reference rather than as a literal
    # at the call site, so this pattern never saw it at all. Issue 20 moved
    # that CSS into css/style.css, and index.html now calls insertAdjacentHTML
    # nowhere.
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


def _without_html_comments(source):
    """Strip HTML comments so a scan reads markup, not prose about markup.

    Same reason as verify_content.without_comments: a comment explaining why
    Font Awesome is gone has to name it.
    """
    return re.sub(r"<!--.*?-->", "", source, flags=re.S)


def _inline_script_bodies(source):
    """Every inline <script> body that holds JavaScript rather than data."""
    tagged = re.compile(r"<script(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script>", re.S)
    data = re.compile(r'\btype\s*=\s*"application/(?:ld\+)?json"', re.I)
    return [body for attrs, body in tagged.findall(source) if not data.search(attrs)]


def _is_font_awesome_class(token):
    """fa and fa-* are Font Awesome 4; fas, fab, far, fal are 5 and 6."""
    return token in ("fa", "fas", "fab", "far", "fal") or token.startswith("fa-")


def check_icons_are_inline_svg():
    """Issue 31 replaced Font Awesome 4.7 with inline SVG symbols.

    Replaces check_font_awesome_is_single_local_version, which asserted one
    local Font Awesome major site-wide. There is no Font Awesome major left
    to be single, so this asserts that none returns, from any source, and
    that every icon the sprite approach draws actually resolves.

    The resolution half is the part nothing else can catch. A <use> naming a
    symbol id the page does not define renders an empty box: no network
    error, no console error, nothing in Lighthouse. The same is true of an
    icon name the portfolio renderer asks for, so its icon("...") calls are
    resolved against index.html's sprite too.
    """
    print("\nIcons are inline SVG, and no Font Awesome remains")

    # HTML_PAGES is discovered from the filesystem, not hardcoded, so a page
    # added after this check was written is scanned automatically.
    pages = {}
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        pages[path.name] = _without_html_comments(source)

    for name, source in pages.items():
        assets = page_assets(source)
        check(
            "cdnjs.cloudflare.com" not in source,
            "%s loads no asset from cdnjs" % name,
        )
        fa_links = [href for href in assets.links if re.search(r"font-?awesome", href, re.I)]
        check(not fa_links, "%s links no Font Awesome stylesheet" % name)

        classes = [token for token in assets.classes if _is_font_awesome_class(token)]
        # The renderer sets classes from string literals, which the markup
        # scan above never sees: el("i", "fa fa-star") was exactly that.
        for body in _inline_script_bodies(source):
            for _, literal in re.findall(r"([\"'`])((?:(?!\1).)*)\1", body):
                # Words of the literal, plus any class attribute written
                # inside one, as in an innerHTML string "<i class='fa x'>".
                words = literal.split()
                for value in re.findall(r"class\s*=\s*[\"']([^\"']*)[\"']", literal):
                    words.extend(value.split())
                classes.extend(token for token in words if _is_font_awesome_class(token))
        check(
            not classes,
            "%s uses no Font Awesome class (fa, fa-*, fas, fab, far, fal)%s"
            % (name, " (found %s)" % ", ".join(sorted(set(classes))) if classes else ""),
        )

        # Read by the parser, so href='#x', href=#x, and xlink:href all count.
        # A <use> must name a symbol on its own page: an external sprite file
        # is a request of its own, and not what this site ships.
        external = [href for href in assets.uses if not href.startswith("#")]
        check(
            not external,
            "%s: every <use> points into the same page%s"
            % (name, " (not: %s)" % ", ".join(external) if external else ""),
        )
        used = [href[1:] for href in assets.uses if href.startswith("#")]
        missing = sorted(set(used) - assets.symbols)
        check(
            not missing,
            "%s: every <use> resolves to a <symbol> on the same page%s"
            % (name, " (missing %s)" % ", ".join(missing) if missing else ""),
        )
        if name in ("index.html", "resume.html"):
            # Both pages draw icons. Finding no <use> at all means the scan
            # broke or the icons vanished, not that everything resolved.
            check(bool(used), "%s draws its icons with <use>" % name)

    index = pages.get("index.html")
    if index is not None:
        script = "\n".join(_inline_script_bodies(index))
        symbols = page_assets(index).symbols
        # Every call, not every literal call: icon(name) with a variable can
        # name anything, and only a literal can be resolved here. The helper's
        # own definition is not a call.
        calls = [
            match for match in re.finditer(r"\bicon\s*\(", script)
            if not re.search(r"function\s+$", script[:match.start()])
        ]
        asked, unresolvable = [], []
        for match in calls:
            literal = re.match(r"""\s*(["'])([\w-]+)\1\s*\)""", script[match.end():])
            if literal:
                asked.append(literal.group(2))
            else:
                unresolvable.append(script[match.start():match.end() + 20].split("\n")[0])
        check(
            not unresolvable,
            "every icon() call in the renderer names its icon with a string literal%s"
            % (" (not: %s)" % "; ".join(unresolvable) if unresolvable else ""),
        )
        if check(bool(asked), "the portfolio renderer draws its icons with icon(name)"):
            missing = sorted(set("icon-" + name for name in asked) - symbols)
            check(
                not missing,
                "every icon the renderer asks for has a symbol in index.html%s"
                % (" (missing %s)" % ", ".join(missing) if missing else ""),
            )


def check_inline_script_syntax():
    """The portfolio renderer lives inline, where node --check cannot see it.

    verify_interactivity.py syntax-checks js/main.js, but the ~90 lines that
    build the portfolio cards sit in an inline <script> in index.html and had
    no gate at all. Extract every inline <script> block, meaning any script
    tag without a src attribute regardless of what other attributes it
    carries, and check it. node is a convenience here, never a project
    dependency.

    A script tag whose type is a data type is checked by a parser that
    matches what it holds, not by node. See below.
    """
    print("\nInline scripts parse")

    have_node = shutil.which("node") is not None
    if not have_node:
        print("  skip  node not found, JavaScript blocks go unchecked")

    # <script\s*> only matched an attribute-less tag, so <script type="module">
    # or <script defer> got no gate at all, and silently: a plain <script>
    # block elsewhere in the same file already satisfied the "has an inline
    # script to check" assertion below. Match any script tag without a src
    # attribute instead; a tag WITH src loads external code that this check
    # is not meant to see.
    tagged = re.compile(r"<script(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script>", re.S)

    # A script tag whose type is a data type holds data, not JavaScript.
    # node --check rejects a JSON-LD block outright, reading the first colon
    # as "SyntaxError: Unexpected token ':'", so routing it to node would
    # make structured data impossible to ship. It still gets gated, just by
    # the parser that matches what it is: a malformed JSON-LD block is
    # invisible to a search engine, and worth catching here exactly as a
    # syntax error in the renderer is.
    data_type = re.compile(r'\btype\s*=\s*"(application/(?:ld\+)?json)"', re.I)

    # Iterating (INDEX, RESUME) exempted any page added later, which is the
    # same silent-exemption bug the HTML_PAGES glob was introduced to fix for
    # the other checks. Sweep every discovered page instead.
    for path in HTML_PAGES:
        source = read_or_fail(path)
        if source is None:
            continue
        blocks = [
            (data_type.search(attrs), body) for attrs, body in tagged.findall(source)
        ]
        name = path.relative_to(ROOT)

        # index.html and resume.html are expected to carry inline script, so
        # finding none there means the extraction pattern broke rather than
        # that the script is gone. A page that legitimately has none,
        # thanks.html or the Termly privacy paste, must not fail for that.
        # A JSON-LD block is not script and does not satisfy this.
        if path in (INDEX, RESUME):
            script_blocks = [body for kind, body in blocks if kind is None]
            if not check(bool(script_blocks), "%s has an inline script to check" % name):
                continue
        elif not blocks:
            print("  skip  %s has no inline script" % name)
            continue

        for number, (kind, body) in enumerate(blocks, start=1):
            if kind is not None:
                try:
                    json.loads(body)
                except ValueError as error:
                    fail(
                        "%s inline %s block %d is not valid JSON: %s"
                        % (name, kind.group(1), number, error)
                    )
                else:
                    print(
                        "  PASS  %s inline %s block %d parses"
                        % (name, kind.group(1), number)
                    )
                continue

            if not have_node:
                continue

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


def _drop_comment_lines(text):
    """Return text's lines with whole-line YAML comments removed.

    The forbidden-token scans read this. A trailing comment is kept, because
    cutting at ` #` is not quote-aware: `run: x ' #' --check-links` would lose
    the flag. Keeping it means a trailing comment that quotes a forbidden
    token fails the check, which is the safe direction.
    """
    return [line.rstrip() for line in text.splitlines()
            if not re.match(r"\s*#", line)]


def _strip_yaml_comments(text):
    """Return text's lines with whole-line and trailing comments removed.

    The structural matching reads this, so a comment beside a key cannot
    change what the key appears to hold. A `#` inside a quoted string is cut
    too; the anchored run-line match then fails closed on what is left.
    """
    return [re.sub(r"\s+#.*$", "", line) for line in _drop_comment_lines(text)]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _nested(lines, start):
    """Return the indices of the non-blank lines nested under lines[start]."""
    body = []
    for number in range(start + 1, len(lines)):
        if not lines[number].strip():
            continue
        if _indent(lines[number]) <= _indent(lines[start]):
            break
        body.append(number)
    return body


def _children(lines, start):
    """Map each key directly under lines[start] to its line index."""
    body = _nested(lines, start)
    if not body:
        return {}
    depth = _indent(lines[body[0]])
    keys = {}
    for number in body:
        match = re.match(r"\s*['\"]?([\w-]+)['\"]?\s*:", lines[number])
        if match and _indent(lines[number]) == depth:
            keys.setdefault(match.group(1), number)
    return keys


def _top_level(lines, key):
    """Index of the indent-0 line for key (quoted or not), or None."""
    for number, line in enumerate(lines):
        if re.match(r"['\"]?%s['\"]?:" % re.escape(key), line):
            return number
    return None


def _value(line):
    """The text after the first colon on a key line."""
    return line.split(":", 1)[1].strip()


def _steps(lines, job):
    """Split the job's steps: list into one dict per step.

    Each dict maps a step key to its value text, plus "_lines" holding every
    line of the step and "_with" holding the lines under its with: key.
    """
    steps_at = _children(lines, job).get("steps")
    if steps_at is None:
        return []
    body = _nested(lines, steps_at)
    if not body:
        return []
    dash = _indent(lines[body[0]])
    steps = []
    for number in body:
        line = lines[number]
        if _indent(line) == dash and line.lstrip().startswith("-"):
            steps.append({"_lines": [], "_with": []})
            line = line[:dash] + " " + line[dash + 1:]
        if not steps:
            continue
        step = steps[-1]
        step["_lines"].append(line)
        match = re.match(r"(\s*)['\"]?([\w-]+)['\"]?\s*:\s*(.*)$", line)
        if match and len(match.group(1)) == dash + 2:
            step[match.group(2)] = match.group(3).strip()
            step["_key"] = match.group(2)
        elif step.get("_key") == "with":
            step["_with"].append(line)
    return steps


def _flow_or_block_items(lines, number):
    """Items of the list on lines[number]: `k: [a, b]` or `- a` lines below."""
    value = _value(lines[number])
    if value.startswith("["):
        items = value.strip("[]").split(",")
    else:
        items = [re.sub(r"^\s*-\s*", "", lines[n]) for n in _nested(lines, number)]
    return [item.strip().strip("'\"") for item in items if item.strip()]


def check_ci_workflow():
    print("\nCI runs every verifier on every pull request")

    text = read_or_fail(WORKFLOW)
    if text is None:
        return
    lines = _strip_yaml_comments(text)
    # Forbidden tokens are searched for in text that still has its trailing
    # comments; see _drop_comment_lines.
    scan = "\n".join(_drop_comment_lines(text))

    # The verify job, located once; every job-scoped rule reads its steps.
    # Branch protection requires the check by name, and with no name:
    # override GitHub reports a job by its id.
    jobs = _top_level(lines, "jobs")
    job = _children(lines, jobs).get("verify") if jobs is not None else None
    if job is not None and _indent(lines[job]) != 2:
        job = None
    if not check(job is not None, "jobs: has a job with id verify"):
        return
    job_keys = _children(lines, job)
    check(
        "name" not in job_keys,
        "the verify job has no name: override, so its check is named verify",
    )
    # Job keys that can switch the gate off: if: or needs: can skip the job,
    # and a skipped required check counts as passed; a matrix renames the
    # check; container: and defaults: (here or at top level) change what runs
    # the steps, and a shell that ignores its script makes every step pass.
    off = sorted(set(job_keys) & {"if", "needs", "strategy", "container",
                                  "services", "defaults"})
    if _top_level(lines, "defaults") is not None:
        off.append("top-level defaults")
    check(not off, "nothing can skip the verify job or replace its shell%s" % (
        " (has %s)" % ", ".join(off) if off else ""))
    steps = _steps(lines, job)
    shells = [step.get("name", "?") for step in steps if "shell" in step]
    check(not shells, "no step sets shell:%s" % (
        " (%s does)" % ", ".join(shells) if shells else ""))

    # A verifier step counts only in the one shape that can fail the job: a
    # bare command on its own run: line. `echo ...`, `... || true`, a run: |
    # block, or the command in a name: would all look present and gate
    # nothing, so a step that mentions a verifier any other way fails.
    ran = []
    for step in steps:
        mentions = any("tools/verify_" in line for line in step["_lines"])
        match = re.fullmatch(r"python3 tools/(verify_\w+\.py)", step.get("run", ""))
        if match:
            ran.append(match.group(1))
            # A plain step is skipped once an earlier one fails, and if: false
            # skips it always; either way it reports nothing.
            condition = step.get("if")
            good = condition in ("${{ !cancelled() }}", "${{ always() }}")
            check(
                good,
                "%s runs under if: ${{ !cancelled() }} or ${{ always() }}%s"
                % (match.group(1), "" if good else " (has %s)" % (condition or "no if:")),
            )
        elif mentions:
            fail("a step mentions a verifier without running it as a bare "
                 "`run: python3 tools/verify_x.py` line: %s"
                 % step.get("name", step.get("run", "?")))
    on_disk = sorted(p.name for p in TOOLS.glob("verify_*.py"))
    missing = sorted(set(on_disk) - set(ran))
    extra = sorted(set(ran) - set(on_disk))
    check(
        not missing and not extra,
        "the verify job runs exactly the %d verifiers in tools/%s%s"
        % (
            len(on_disk),
            " (not run: %s)" % ", ".join(missing) if missing else "",
            " (not on disk: %s)" % ", ".join(extra) if extra else "",
        ),
    )
    twice = sorted(name for name in set(ran) if ran.count(name) > 1)
    check(not twice, "no verifier runs twice%s" % (
        " (%s does)" % ", ".join(twice) if twice else ""))
    check("continue-on-error" not in scan, "nothing sets continue-on-error")

    # Actions: three known ones, each pinned to a major tag at minimum or a
    # full SHA. A tag can be moved, but a branch moves by design.
    allowed = {"actions/checkout", "actions/setup-python", "actions/setup-node"}
    uses = re.findall(r"uses:\s*['\"]?([^'\"\s]+)", scan)
    pinned = re.compile(r"[\w.-]+/[\w./-]+@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$")
    loose = [u for u in uses if not pinned.match(u) or u.split("@")[0] not in allowed]
    check(
        uses and not loose,
        "every uses: is checkout, setup-python, or setup-node, pinned to a "
        "version tag or a full SHA%s" % (" (not: %s)" % ", ".join(loose) if loose else ""),
    )
    # Without node, check_inline_script_syntax here and the js/main.js gate
    # in verify_interactivity.py skip instead of failing.
    in_job = {s.get("uses", "").strip("'\"").split("@")[0]: s for s in steps}
    check("actions/setup-node" in in_job, "the verify job sets up node")
    check("actions/setup-python" in in_job, "the verify job sets up Python")
    # A setup step under an if: can be skipped, and then node is silently
    # absent again.
    gated = sorted(name for name, step in in_job.items() if name and "if" in step)
    check(not gated, "checkout and setup steps run unconditionally%s" % (
        " (%s has an if:)" % ", ".join(gated) if gated else ""))
    checkout = in_job.get("actions/checkout")
    check(
        checkout is not None
        and any(re.fullmatch(r"\s*persist-credentials:\s*false", l) for l in checkout["_with"]),
        "the verify job checks out with persist-credentials: false",
    )

    # Least privilege: an indent-0 permissions block granting contents: read,
    # and write granted nowhere, in block, flow, or write-all form.
    top = _top_level(lines, "permissions")
    check(
        top is not None and _value(lines[top]) == ""
        and any(re.fullmatch(r"\s+contents:\s*read", lines[n]) for n in _nested(lines, top)),
        "top-level permissions grant contents: read",
    )
    check(
        not re.search(r":\s*['\"]?write['\"]?\s*([,}#]|$)|write-all", scan, re.M),
        "no permission is granted write",
    )
    check(
        not re.search(r"\bsecrets\b|GITHUB_TOKEN|github\.token", scan),
        "the workflow references no secrets, GITHUB_TOKEN, or github.token",
    )
    # --check-links and installs need the network; a flaky wifi failure in
    # the gate teaches people to ignore it. The verifiers need no packages.
    check("--check-links" not in scan, "no step passes --check-links")
    network = sorted(set(re.findall(r"\bpip3? install\b|\bnpm\b|\bnpx\b|\bcurl\b|\bwget\b", scan)))
    check(not network, "no step installs or fetches anything%s" % (
        " (found: %s)" % ", ".join(network) if network else ""))

    # Triggers. A filtered-out pull request never reports the required check
    # and sits pending forever, so pull_request takes no filters, and
    # pull_request_target runs base-branch code with a write token.
    check("pull_request_target" not in scan, "nothing runs on pull_request_target")
    trig = _top_level(lines, "on")
    events = _children(lines, trig) if trig is not None else {}
    if check("pull_request" in events, "the workflow runs on pull_request"):
        keys = _children(lines, events["pull_request"])
        filters = sorted(set(keys) & {"paths", "paths-ignore", "types", "branches-ignore"})
        check(not filters, "pull_request has no paths, types, or branches-ignore filter%s" % (
            " (has %s)" % ", ".join(filters) if filters else ""))
        check(
            "branches" not in keys or "main" in _flow_or_block_items(lines, keys["branches"]),
            "pull_request branches:, if present, includes main",
        )
    if check("push" in events, "the workflow runs on push"):
        keys = _children(lines, events["push"])
        check(
            "branches" in keys and "main" in _flow_or_block_items(lines, keys["branches"]),
            "push names main under branches:",
        )
        filters = sorted(set(keys) & {"branches-ignore", "tags", "tags-ignore",
                                      "paths", "paths-ignore"})
        check(not filters, "push has no other filter%s" % (
            " (has %s)" % ", ".join(filters) if filters else ""))


def main():
    check_no_end_of_life_library()
    check_css_imports_are_first_party()
    check_no_unescaped_interpolation()
    check_repo_urls_are_scheme_validated()
    check_no_plain_http_assets()
    check_no_ie_conditional_shims()
    check_icons_are_inline_svg()
    check_inline_script_syntax()
    check_ci_workflow()

    print()
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
