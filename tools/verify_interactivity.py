#!/usr/bin/env python3
"""Verify the site's interactive JavaScript is actually wired up.

Standalone, standard library only, run by hand from the repo root:

    python3 tools/verify_interactivity.py

Exits 0 when the issue #16 acceptance criteria still hold at the source
level: index.html loads js/main.js, every section a nav link points at takes
part in active-link tracking, every skill bar carries a data-percent instead
of a hardcoded inline width, the portfolio card click handler yields to real
anchors, and js/main.js references nothing the markup does not contain.

Issue #31 retired jQuery and Bootstrap's JavaScript. main.js is vanilla, so
the check that it loads after jQuery became a check that no page loads
either library, and three checks hold the pieces that replaced them: the
mobile menu toggle is a plain <button> that states its own aria-expanded and
aria-controls, smooth scrolling is the browser's own (CSS scroll-behavior,
only when the visitor has not asked for reduced motion, plus a
scroll-margin-top that clears the fixed header), and main.js neither calls a
jQuery or Bootstrap API nor scrolls or cancels anything itself that would
fight that native scroll.

Issue #33 adds one more: focus follows an activated in-page link. Every
link target is a .one-page-section with no static tabindex; js/main.js makes
the target focusable only for the click that activates the link, so native
fragment navigation moves focus into it, and removes the attribute again;
and css/style.css suppresses the outline on a focused .one-page-section,
which is a reading position and not a control.

Behavior (does the navbar actually go sticky, does the bar actually
animate, does a nav link land below the header) cannot be checked here.
Drive that in a browser.
"""

import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
# Every page at the repo root, for the one check that is about every page:
# no page may load jQuery or Bootstrap. Same glob the other verifiers use.
HTML_PAGES = sorted(ROOT.glob("*.html"))
MAIN_JS = ROOT / "js" / "main.js"
STYLE_CSS = ROOT / "css" / "style.css"

failures = []


def fail(message):
    failures.append(message)


class IndexFacts(HTMLParser):
    """Collect the few facts about index.html that the checks below need."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []        # src of every <script src=...>
        self.ids = {}            # id -> set of class tokens
        self.nav_targets = []    # fragment of every <a class="scroll" href="#...">
        self.fragment_targets = []  # fragment of every <a href="#...">, any class
        self.tabindex = {}       # id -> tabindex attribute (None when absent)
        self.tabindexes = []     # (tag, id, value) of every element with a tabindex
        self.progress_bars = []  # (data-percent, style) per .progress-bar-line
        self.parallax = []       # tag name of every element with class "parallax"
        self.toggles = []        # attrs of every element with class "navbar-toggle"
        self.toggle_text = []    # text inside each toggle, by index
        self.nav_lists = []      # id chain of the elements enclosing each ul.navbar-nav
        self._open = []          # stack of (tag, id) for the containment test
        self._in_toggle = None

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())

        if tag == "script" and attr.get("src"):
            self.scripts.append(attr["src"])

        if attr.get("id"):
            self.ids[attr["id"]] = classes
            # A bare `tabindex` has the value None from HTMLParser; record it
            # as "" so it still reads as present, which it is to
            # hasAttribute("tabindex") and so to the click listener.
            self.tabindex[attr["id"]] = (attr["tabindex"] or "") if "tabindex" in attr else None

        if "tabindex" in attr:
            self.tabindexes.append((tag, attr.get("id"), attr["tabindex"]))

        if tag == "a":
            href = attr.get("href") or ""
            if href.startswith("#") and len(href) > 1 and href[1:] not in self.fragment_targets:
                self.fragment_targets.append(href[1:])

        if tag == "a" and "scroll" in classes:
            href = attr.get("href") or ""
            if href.startswith("#") and len(href) > 1:
                self.nav_targets.append(href[1:])

        if "progress-bar-line" in classes:
            self.progress_bars.append((attr.get("data-percent"), attr.get("style")))

        if "parallax" in classes:
            self.parallax.append(tag)

        if "navbar-toggle" in classes:
            self.toggles.append(dict(attr, _tag=tag))
            self.toggle_text.append("")
            self._in_toggle = len(self.toggles) - 1

        if tag == "ul" and "navbar-nav" in classes:
            self.nav_lists.append([i for _, i in self._open if i])

        if tag not in VOID:
            self._open.append((tag, attr.get("id")))

    def handle_endtag(self, tag):
        if tag == "button" and self._in_toggle is not None:
            self._in_toggle = None
        # Unwind to the matching open tag, so one stray close tag cannot
        # leave the whole stack shifted.
        for depth in range(len(self._open) - 1, -1, -1):
            if self._open[depth][0] == tag:
                del self._open[depth:]
                break

    def handle_data(self, data):
        if self._in_toggle is not None:
            self.toggle_text[self._in_toggle] += data


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "source", "track", "wbr"}


def check_script_tag(facts):
    """main.js has to load, and no page may load jQuery or Bootstrap.

    Until issue 31 this asserted that main.js loaded after jQuery, because
    main.js was jQuery code. It is vanilla now, so the ordering rule has
    nothing left to order, and the risk turned around: a jQuery or Bootstrap
    tag coming back is 127 KB of end-of-life library that nothing calls.
    Every page is swept, not just index.html.
    """
    # ./js/main.js and /js/main.js load the same file; the site serves from
    # the root, so all three spellings count.
    normalized = [re.sub(r"^(?:\./|/)", "", src) for src in facts.scripts]
    if "js/main.js" not in normalized:
        fail(
            "index.html does not load js/main.js. The tag was dropped in "
            "eba0f7b and every interaction in that file died with it."
        )

    for path in HTML_PAGES:
        page = IndexFacts()
        page.feed(path.read_text(encoding="utf-8", errors="replace"))
        for src in page.scripts:
            if re.search(r"jquery|bootstrap", src, re.I):
                fail(
                    "%s loads %s. jQuery and Bootstrap's JavaScript were "
                    "retired in issue 31; main.js is vanilla and nothing "
                    "calls either." % (path.name, src)
                )


def check_nav_toggle(facts):
    """The mobile menu toggle is a plain button that states its own state.

    Bootstrap's collapse plugin used to read data-toggle and data-target
    and flip aria-expanded for it. With the plugin gone, the markup has to
    carry the contract itself: a real <button type="button"> (a bare
    <button> inside a form would submit it), aria-expanded starting at
    "false" because the menu starts closed, and aria-controls naming the
    element that holds the nav links, which is what a screen reader offers
    to jump to. data-toggle and data-target are dead attributes now, and
    leaving them suggests a plugin that is not there.
    """
    if len(facts.toggles) != 1:
        fail("index.html has %d .navbar-toggle elements, expected exactly one." % len(facts.toggles))
        return
    toggle = facts.toggles[0]

    if toggle["_tag"] != "button" or toggle.get("type") != "button":
        fail('The nav toggle is not a <button type="button">.')
    if toggle.get("aria-expanded") != "false":
        fail(
            'The nav toggle does not start at aria-expanded="false" (has %r).'
            % toggle.get("aria-expanded")
        )
    for dead in ("data-toggle", "data-target"):
        if dead in toggle:
            fail("The nav toggle still carries %s, which only Bootstrap's JavaScript read." % dead)

    controls = toggle.get("aria-controls")
    if not controls:
        fail("The nav toggle has no aria-controls.")
    elif controls not in facts.ids:
        fail("The nav toggle's aria-controls names #%s, which does not exist." % controls)
    elif not facts.nav_lists or not all(controls in chain for chain in facts.nav_lists):
        fail(
            "The nav toggle's aria-controls names #%s, which does not wrap the "
            "nav link list." % controls
        )

    named = (toggle.get("aria-label") or "").strip() or facts.toggle_text[0].strip()
    if not named:
        fail("The nav toggle has no accessible name.")


def media_blocks(css, condition):
    """(start, end) spans of every @media block whose prelude matches condition."""
    spans = []
    for match in re.finditer(r"@media[^{]*" + condition + r"[^{]*\{", css):
        depth, index = 1, match.end()
        while depth and index < len(css):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
            index += 1
        spans.append((match.start(), index))
    return spans


def strip_js_comments(code):
    """JavaScript with its /* */ and // comments removed, strings intact.

    Quote-aware: a // or /* inside a string literal, such as "https://..."
    or a path with a doubled slash, is part of the string and is kept. A
    comment that quotes code, such as `// icon(name) returns an inline
    <svg>`, is gone before any scan reads the code. Regular expression
    literals are not recognized; the scripts here have none that hold a
    quote or a //.
    """
    out = []
    index, length = 0, len(code)
    quote = None
    while index < length:
        char = code[index]
        if quote:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(code[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
            out.append(char)
            index += 1
            continue
        if code.startswith("/*", index):
            end = code.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        if code.startswith("//", index):
            end = code.find("\n", index)
            index = length if end == -1 else end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def check_native_smooth_scroll(css, js):
    """Smooth scrolling is the browser's, and nothing in main.js fights it.

    jQuery's .animate() used to drive every nav link and the back-to-top
    button, and subtracted the header height by hand. Issue 31 hands both
    jobs to CSS: scroll-behavior: smooth on the root, and a scroll-margin-top
    on each section so a fragment lands below the fixed header instead of
    under it.

    scroll-behavior has to sit inside @media (prefers-reduced-motion:
    no-preference). Unconditional, it animates every jump for a visitor who
    asked the OS for no motion, which the old code honored by passing a zero
    duration.

    And main.js must not scroll or cancel a click itself. A handler that
    calls preventDefault on a nav link, or scrolls with scrollTo or by
    assigning scrollTop, races the native scroll and loses the hash update
    that native fragment navigation gives for free.
    """
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # The query must be exactly the no-preference test (optionally limited to
    # screen). A list like `(prefers-reduced-motion: no-preference), all`
    # matches everyone, which is no condition at all.
    allowed = [
        span for span in media_blocks(css_code, r"prefers-reduced-motion\s*:\s*no-preference")
        if re.fullmatch(
            r"@media\s*(?:(?:only\s+)?screen\s+and\s*)?\(\s*prefers-reduced-motion\s*:\s*no-preference\s*\)\s*\{",
            css_code[span[0]:css_code.index("{", span[0]) + 1],
        )
    ]
    smooth = [m.start() for m in re.finditer(r"scroll-behavior\s*:\s*smooth", css_code)]
    if not smooth:
        fail("css/style.css never sets scroll-behavior: smooth, so nav links jump.")
    for position in smooth:
        if not any(start < position < end for start, end in allowed):
            fail(
                "css/style.css sets scroll-behavior: smooth outside "
                "@media (prefers-reduced-motion: no-preference), so it animates "
                "for visitors who asked for reduced motion."
            )
        rule = css_code.rfind("{", 0, position)
        opened = max(css_code.rfind("}", 0, rule), css_code.rfind("{", 0, rule))
        selector = css_code[opened + 1:rule].strip()
        # html alone, or html under the class check_deep_link_is_not_animated
        # requires; never a section, a container, or body.
        if not re.fullmatch(r"html(\.[\w-]+)?", selector):
            fail("scroll-behavior: smooth is set on %r; it belongs on html alone." % selector)

    # A positive length: scroll-margin-top: 0 declares the property and
    # still lands every heading under the header.
    margin = [
        m for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_code)
        if any(part.strip() == ".one-page-section" for part in m.group(1).split(","))
        and re.search(r"scroll-margin-top\s*:\s*(?:[1-9]\d*(?:\.\d+)?|0?\.\d*[1-9]\d*)(?:px|r?em)\b", m.group(2))
    ]
    if not margin:
        fail(
            ".one-page-section declares no positive scroll-margin-top, so a nav "
            "link lands the section heading under the fixed header."
        )

    js_code = strip_js_comments(js)
    # Patterns, not literal strings: `scrollTop=0`, `scrollTop += 1`,
    # `scrollTop++`, `window.scroll(0, 0)`, and `scrollBy (0, 1)` are all
    # scripted scrolls.
    for pattern, label, reason in (
        (r"\bscroll(?:To|By)?\s*\(", "scroll(), scrollTo(), or scrollBy()", "scrolling is native now"),
        (r"\bscrollIntoView\s*\(", "scrollIntoView()", "scrolling is native now"),
        (r"\bscroll(?:Top|Left)\s*(?:[-+*/]?=(?!=)|\+\+|--)|(?:\+\+|--)\s*[\w$.]*\bscroll(?:Top|Left)\b",
         "an assignment to scrollTop or scrollLeft",
         "assigning a scroll offset is a scripted scroll; scrolling is native now"),
        (r"\bpreventDefault\b", "preventDefault",
         "cancelling a click stops the native fragment navigation and its hash update"),
    ):
        if re.search(pattern, js_code):
            fail("js/main.js contains %s: %s." % (label, reason))


def check_nav_targets(facts):
    """changeActiveNavLink() only sees sections carrying one-page-section."""
    for target in facts.nav_targets:
        classes = facts.ids.get(target)
        if classes is None:
            fail("A nav link points at #%s but no element has that id." % target)
        elif "one-page-section" not in classes:
            fail(
                "#%s lacks the one-page-section class, so its nav link never "
                "highlights." % target
            )


# @media preludes under which a rule applies to every on-screen visitor.
SCREEN_MEDIA = r"@media\s+(?:only\s+)?(?:screen|all)"

# The one link the handler serves: any anchor whose href is a fragment.
FRAGMENT_LINK = r"""closest\(\s*(["'])a\[href\^=(?:"#"|'#')\]\1\s*\)"""


def outline_declarations(body):
    """(state, important) per outline, outline-style, or outline-width declaration.

    state is 'hidden' or 'visible'. `outline: none; outline-style: solid`
    paints a ring, and so, for this check, does `outline: none;
    outline-width: 2px`: either one undoes the suppression the rule exists
    for. `hidden` is not a valid outline-style value: Chromium drops the
    declaration and paints the UA ring, so it counts as visible here.
    """
    declarations = []
    for prop, value in re.findall(r"(?<![-\w])(outline(?:-style|-width)?)\s*:\s*([^;]+)", body):
        important = bool(re.search(r"!\s*important", value, re.I))
        value = re.sub(r"!\s*important", "", value, flags=re.I).strip().lower()
        if prop == "outline":
            state = "hidden" if value in ("none", "0", "0px") else "visible"
        elif prop == "outline-style":
            state = "hidden" if value == "none" else "visible"
        else:
            state = "hidden" if re.fullmatch(r"0(?:\.0+)?(?:px|r?em)?", value) else "visible"
        declarations.append((state, important))
    return declarations


class OutlineCascade:
    """The cascade, reduced to what one selector's outline needs.

    An !important declaration outranks every normal one wherever it sits,
    and within each group the last declaration wins. `{ outline: 2px solid
    red !important }` followed by `{ outline: none }` paints the ring.
    """

    def __init__(self):
        self.normal = None
        self.important = None

    def add(self, declarations):
        for state, important in declarations:
            if important:
                self.important = state
            else:
                self.normal = state

    def state(self):
        return self.important if self.important is not None else self.normal


def outline_state(body):
    """'hidden', 'visible', or None: what one declaration block does to the outline."""
    cascade = OutlineCascade()
    cascade.add(outline_declarations(body))
    return cascade.state()


def html_integer(value):
    """value parsed by HTML's rules for parsing integers, or None.

    Leading ASCII whitespace is skipped, one optional sign is read, then the
    digits; anything after them is ignored. So tabindex="1a" is 1 and
    tabindex=" 0" is 0, exactly as a browser reads them, and a value with no
    leading integer is ignored by the browser and returns None here. That
    includes a bare attribute (value None) and non-ASCII digits such as an
    Arabic-Indic one: the rules accept ASCII digits only.
    """
    if value is None:
        return None
    match = re.match(r"[\t\n\f\r ]*([-+]?)([0-9]+)", value)
    if match is None:
        return None
    number = int(match.group(2))
    return -number if match.group(1) == "-" else number


def check_link_targets_take_focus(facts, css, js):
    """Focus moves into a section only when a link to it is activated.

    Issue 33. Native fragment navigation runs the focusing steps on its
    target, but a plain section is not focusable, so Chromium blurs the link
    and leaves focus on <body>: the page scrolls and nothing tells assistive
    technology the reading position moved.

    A static tabindex="-1" on each section fixed that and broke something
    else: a mouse click or tap on any non-control content inside a section
    then focuses the section, so the next Tab restarts at the section's
    first control. At 375px, a click on a lower portfolio card at scrollY
    4937 followed by Tab jumped back to the first card's Code link at 4150.
    So no section may carry a static tabindex, and no element may carry a
    tabindex of 0 or more, which would put it into the tab order. Instead
    js/main.js listens for clicks on document, and for an anchor whose href
    is a fragment it sets tabindex="-1" on the target without cancelling the
    click, then removes the attribute again, so a section is focusable only
    for the moment a link moves focus into it. A bare "#" names no element,
    so back to top is untouched.

    Every link target has to be a .one-page-section, because that is the
    selector the outline suppression names. The focused section is a reading
    position, not a control, and its UA ring would outline a box several
    viewports tall. The last .one-page-section:focus rule that applies on
    screen (outside @media, or under @media screen or all) decides, and it
    must leave the outline hidden; a rule under any other query except print
    that paints an outline on it, or on .one-page-section:focus-visible,
    fails, since it shows at some width. An !important declaration outranks
    every normal one, as in the browser.

    History traversal runs no click, and traversal to an entry with no
    fragment runs no focusing step either, so Back from #contact to the
    unhashed top of the page left focus in #contact and the next Tab jumped
    back down to its first control. js/main.js therefore also listens on
    window for hashchange or popstate (addEventListener, or the
    onhashchange / onpopstate property) and blurs (or strips the attribute
    from) a section it made focusable that the new hash does not name. Both
    events fire on window only, so a listener on document does not count.

    The js/main.js assertions are presence checks, by this repo's
    convention: they prove the handler's pieces are there, not what they do.
    The browser drive proves the behavior.
    """
    for target in facts.fragment_targets:
        classes = facts.ids.get(target)
        if classes is None:
            fail("An in-page link points at #%s but no element has that id." % target)
        elif "one-page-section" not in classes:
            fail(
                "An in-page link points at #%s, which is not a .one-page-section, "
                "so the outline suppression does not cover it and focusing it "
                "paints a ring around the whole element." % target
            )
        elif facts.tabindex.get(target) is not None:
            fail(
                "#%s carries a static %s. A mouse click or tap inside the section "
                "then focuses it, and the next Tab restarts at its first control; "
                "even a value the browser ignores makes hasAttribute(\"tabindex\") "
                "true, so the click listener skips the section and focus never "
                "moves. js/main.js adds the attribute only when a link is "
                "activated." % (
                    target,
                    'tabindex="%s"' % facts.tabindex[target] if facts.tabindex[target]
                    else "bare tabindex attribute",
                )
            )

    for tag, element_id, value in facts.tabindexes:
        number = html_integer(value)
        if number is not None and number >= 0:
            fail(
                '<%s%s> carries tabindex="%s", which puts it into the tab order.'
                % (tag, "#" + element_id if element_id else "", value)
            )

    js_code = strip_js_comments(js)
    spans = function_spans(js_code)
    listener = r"document\s*\.\s*addEventListener\(\s*([\"'])click\1\s*,\s*"
    handlers = [span for span in spans if span[0] is None and re.search(listener + r"$", span[3])]
    for name in re.findall(listener + r"([A-Za-z_$][\w$]*)\s*[,)]", js_code):
        handlers.extend(span for span in spans if span[0] == name[1])
    bodies = [js_code[span[1]:span[2]] for span in handlers]
    found = [
        body for body in bodies
        if re.search(FRAGMENT_LINK, body)
        and re.search(r"""setAttribute\(\s*(["'])tabindex\1\s*,\s*(["'])-1\2\s*\)""", body)
    ]
    if not found:
        fail(
            "js/main.js has no click listener on document that selects the "
            "activated fragment link with closest('a[href^=\"#\"]') and sets "
            "tabindex=\"-1\" on its target, so a nav link scrolls but leaves "
            "focus on <body>."
        )
    elif not any(re.search(r"""removeAttribute\(\s*(["'])tabindex\1\s*\)""", body) for body in found):
        fail(
            "js/main.js sets tabindex=\"-1\" on a link target but never removes "
            "it, which leaves the section permanently focusable and brings back "
            "the mouse and touch Tab order regression."
        )

    # hashchange and popstate fire on window only; a listener on document
    # never runs.
    history = (
        r"(?<![\w$.])window\s*\.\s*(?:addEventListener\(\s*([\"'])(?:hashchange|popstate)\1\s*,"
        r"|on(?:hashchange|popstate)\s*=(?!=))\s*"
    )
    cleanups = [span for span in spans if span[0] is None and re.search(history + r"$", span[3])]
    for name in re.findall(history + r"([A-Za-z_$][\w$]*)\s*[,);]?", js_code):
        cleanups.extend(span for span in spans if span[0] == name[1])
    if not any(
        re.search(r"""\.blur\(\s*\)|removeAttribute\(\s*(["'])tabindex\1\s*\)""", js_code[span[1]:span[2]])
        for span in cleanups
    ):
        fail(
            "js/main.js has no hashchange or popstate listener on window that blurs a "
            "section it made focusable or removes its tabindex, so Back to an "
            "entry with no fragment leaves focus in the old section and the "
            "next Tab jumps back down to it."
        )

    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    decided = OutlineCascade()
    for media, selector, body in css_rules(css_code):
        parts = [part.strip() for part in selector.split(",")]
        on_screen = all(re.fullmatch(SCREEN_MEDIA, prelude) for prelude in media)
        printed = any(re.fullmatch(r"@media\s+(?:only\s+)?print", prelude) for prelude in media)
        state = outline_state(body)
        if ".one-page-section:focus" in parts and on_screen and state is not None:
            decided.add(outline_declarations(body))
        elif (
            not on_screen and not printed and state == "visible"
            and ({".one-page-section:focus", ".one-page-section:focus-visible"} & set(parts))
        ):
            fail(
                "%r paints an outline on a focused section inside %s."
                % (selector, " ".join(media))
            )
        if on_screen and ".one-page-section:focus-visible" in parts and state == "visible":
            fail("%r paints an outline on a focused section." % selector)
    if decided.state() != "hidden":
        fail(
            "css/style.css does not leave the outline hidden on a focused "
            ".one-page-section (the last on-screen `.one-page-section:focus` rule "
            "must set outline: none), so a nav link paints a focus ring around "
            "the whole section it lands on."
        )


def check_deep_link_is_not_animated(css, js):
    """A deep link must land below the header, not short of it.

    Found driving issue 31. With scroll-behavior: smooth on html from the
    first paint, Chrome animates the initial jump to a URL's fragment, and it
    fixes the animation's end point when it starts. The page is still moving
    then: the portfolio cards render from projects.json and Lato arrives
    from Google Fonts, both above #contact. So /#contact ended its animation
    with the section 11px below the top at 375px and 37px at 1440px, under
    the 63px header, where an instant jump re-resolves against the final
    layout and lands flush.

    So smooth scrolling has to start only once the page has loaded: every
    scroll-behavior: smooth must sit on html qualified by a class, and
    js/main.js must be what adds that class to the root element.
    """
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    js_code = re.sub(r"/\*.*?\*/|//[^\n]*", "", js, flags=re.S)
    classes = set()
    for match in re.finditer(r"scroll-behavior\s*:\s*smooth", css_code):
        rule = css_code.rfind("{", 0, match.start())
        opened = max(css_code.rfind("}", 0, rule), css_code.rfind("{", 0, rule))
        selector = css_code[opened + 1:rule].strip()
        gated = re.fullmatch(r"html\.([\w-]+)", selector)
        if gated is None:
            fail(
                "scroll-behavior: smooth is on %r from the first paint, so the "
                "initial jump to a URL fragment animates toward a target the "
                "loading page then moves, and /#contact lands under the header. "
                "Put it on html.<class> and add the class from js/main.js once "
                "the page has loaded." % selector
            )
        else:
            classes.add(gated.group(1))
    for name in sorted(classes):
        added = re.search(
            r"document\.documentElement\.classList\.add\(\s*([\"'])%s\1\s*\)" % re.escape(name),
            js_code,
        )
        if added is None:
            fail(
                "css/style.css gates smooth scrolling on html.%s, but js/main.js "
                "never adds that class to the root element, so nav links jump." % name
            )


def named_function_spans(js):
    """(name, start, end) of every `function name(...) { ... }` body in js."""
    spans = []
    for match in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", js):
        depth, index = 1, match.end()
        while depth and index < len(js):
            if js[index] == "{":
                depth += 1
            elif js[index] == "}":
                depth -= 1
            index += 1
        spans.append((match.group(1), match.end(), index))
    return spans


def function_spans(js):
    """(name or None, start, end, text before) of every function body in js.

    Named declarations, anonymous function expressions, and arrow functions
    with a block body. The text before an anonymous one is what it is passed
    to, so a load listener written inline can be recognized.
    """
    spans = []
    pattern = re.compile(
        r"\bfunction\s*([A-Za-z_$][\w$]*)?\s*\([^)]*\)\s*\{"
        r"|(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{"
    )
    for match in pattern.finditer(js):
        depth, index = 1, match.end()
        while depth and index < len(js):
            if js[index] == "{":
                depth += 1
            elif js[index] == "}":
                depth -= 1
            index += 1
        spans.append((match.group(1), match.end(), index, js[max(0, match.start() - 80):match.start()]))
    return spans


# window.addEventListener("load", ...) or a bare addEventListener("load", ...)
# at global scope; never document.addEventListener("load"), which never fires.
LOAD_LISTENER = r"(?:(?<![\w$.])window\s*\.\s*|(?<![\w$.]))addEventListener\(\s*([\"'])load\1\s*,\s*"


def check_smooth_scroll_starts_on_load(css, js):
    """The smooth-scroll class is added from the load path, not during init.

    check_deep_link_is_not_animated requires smooth scrolling to be keyed on
    a class main.js adds. Adding it while main.js initializes, which runs
    before the portfolio cards and the webfont arrive, would bring back the
    deep-link bug that check exists for.

    A function is on the load path when window's load listener is it (named,
    with or without an options argument such as { once: true }, or written
    inline), when a function on the load path names it (a named
    requestAnimationFrame or setTimeout callback, or a direct call), or when
    it is an anonymous function inside one. Every place main.js adds the
    class must be inside a function on that path. A listener on document
    does not count: load fires on window.
    """
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    js_code = strip_js_comments(js)
    classes = set(re.findall(r"html\.([\w-]+)\s*\{[^}]*scroll-behavior\s*:\s*smooth", css_code))
    spans = function_spans(js_code)

    def enclosing(span):
        outer = [o for o in spans if o is not span and o[1] <= span[1] and span[2] <= o[2]]
        return min(outer, key=lambda o: o[2] - o[1]) if outer else None

    memo = {}

    def on_load_path(span, depth=0):
        key = (span[1], span[2])
        if key in memo or depth > 8:
            return memo.get(key, False)
        memo[key] = False
        name, start, end, before = span
        if name is None:
            result = bool(re.search(LOAD_LISTENER + r"$", before)) or (
                enclosing(span) is not None and on_load_path(enclosing(span), depth + 1)
            )
        else:
            result = bool(re.search(LOAD_LISTENER + re.escape(name) + r"\s*[,)]", js_code))
            if not result:
                for other in spans:
                    if other is span or (other[1] <= start and end <= other[2] and other[0] == name):
                        continue
                    if other[1] <= start < other[2]:
                        continue  # a function enclosing this one does not call it by containing it
                    body = js_code[other[1]:other[2]]
                    if re.search(r"(?<![\w$.])%s\b" % re.escape(name), body) and on_load_path(other, depth + 1):
                        result = True
                        break
        memo[key] = result
        return result

    for name in sorted(classes):
        adds = list(re.finditer(
            r"document\.documentElement\.classList\.add\(\s*([\"'])%s\1\s*\)" % re.escape(name),
            js_code,
        ))
        for add in adds:
            around = [span for span in spans if span[1] <= add.start() < span[2]]
            innermost = min(around, key=lambda span: span[2] - span[1]) if around else None
            if innermost is None or not on_load_path(innermost):
                fail(
                    "js/main.js adds the %s class outside the window load path (%s), "
                    "so smooth scrolling can start before the page has settled and "
                    "a deep link animates short of its section."
                    % (name, "in %s()" % (innermost[0] or "an anonymous function")
                       if innermost else "at top level")
                )


NAV_DISPLAY_TOKENS = ("navbar-collapse", "bm-navbar", "navbar-toggle")


def capped_media(prelude):
    """True when a @media prelude puts an upper bound on the width.

    max-width, range syntax with the width on the small side (width < 768px,
    width <= 767px, 768px > width), and a negated min-width all cap it.
    """
    return bool(
        re.search(r"max-width", prelude)
        or re.search(r"\bwidth\s*<", prelude)
        or re.search(r">=?\s*width\b", prelude)
        or re.search(r"\bnot\b[^{]*min-width", prelude)
    )


def nav_tokens(selector):
    """Which nav elements a selector's subject is, ignoring pseudo-elements.

    Only the last compound decides what the rule styles: `.nav-sticky
    .navbar-collapse` styles the menu, `.navbar-collapse a` styles links in
    it, and `.navbar-collapse::after` styles a clearfix box, not the menu.
    """
    subject = re.split(r"\s*[>+~]\s*|\s+", selector.strip())[-1]
    if re.search(r"::?(?:before|after|first-line|first-letter|marker|placeholder)\b", subject):
        return []
    return [token for token in NAV_DISPLAY_TOKENS if re.search(r"[.#]%s(?![\w-])" % token, subject)]


def check_nav_breakpoints(css):
    """The two nav states each own their width range, by any selector or syntax.

    Review round 2 of issue 31. check_collapse_covers_every_width (frozen)
    reads `max-width` and the class selectors. This one adds what it does not
    see: a range-syntax cap such as (width < 768px) and the #bm-navbar id
    decide nothing about display either; the base rules keep the toggle
    visible and the menu hidden unless it is .is-open or animating; and the
    min-width: 768px block both shows the menu and hides the toggle, without
    which the desktop nav vanishes or a dead toggle shows beside it.
    """
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    shows_menu = hides_toggle = False
    for media, selector, body in css_rules(css_code):
        display = re.search(r"(?<![-\w])display\s*:\s*([^;]+)", body)
        if not display:
            continue
        value = re.sub(r"!\s*important", "", display.group(1)).strip().lower()
        for part in (part.strip() for part in selector.split(",")):
            tokens = nav_tokens(part)
            if not tokens:
                continue
            if any(capped_media(prelude) for prelude in media):
                fail(
                    "%r sets display inside %s, a width-capped query; the mobile "
                    "nav state has to be the base rule." % (part, " ".join(media))
                )
            if not media:
                if "navbar-toggle" in tokens and value == "none":
                    fail("%r hides the menu toggle at every width." % part)
                if (
                    {"navbar-collapse", "bm-navbar"} & set(tokens)
                    and value != "none"
                    and not re.search(r"\.is-(?:open|collapsing)\b", part)
                ):
                    fail(
                        "%r shows the mobile menu at every width; only .is-open "
                        "may, below 768px." % part
                    )
            if media and all(
                re.search(r"min-width\s*:\s*768px|width\s*>=\s*768px|768px\s*<=\s*width", prelude)
                for prelude in media
            ):
                if {"navbar-collapse", "bm-navbar"} & set(tokens) and value in ("block", "flex"):
                    shows_menu = True
                if "navbar-toggle" in tokens and value == "none":
                    hides_toggle = True
    if not shows_menu:
        fail(
            "No min-width: 768px rule shows .navbar-collapse (display: block or "
            "flex), so the desktop nav links are hidden."
        )
    if not hides_toggle:
        fail(
            "No min-width: 768px rule hides .navbar-toggle, so a toggle that "
            "does nothing shows beside the inline links."
        )


def css_rules(css, media=()):
    """Every style rule as (enclosing @media preludes, selector, declarations).

    A small brace walker, enough for this stylesheet: it descends into any
    at-rule block and records the prelude of each @media it passes through.
    """
    rules = []
    index = 0
    while index < len(css):
        brace = css.find("{", index)
        if brace == -1:
            break
        prelude = css[index:brace].strip()
        depth, end = 1, brace + 1
        while depth and end < len(css):
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        body = css[brace + 1:end - 1]
        if prelude.startswith("@"):
            inner = media + (prelude,) if prelude.startswith("@media") else media
            rules.extend(css_rules(body, inner))
        else:
            rules.append((media, prelude, body))
        index = end
    return rules


def check_collapse_covers_every_width(css):
    """The mobile menu is hidden at every width the inline nav does not cover.

    Found in review of issue 31. The hiding rules sat in @media (max-width:
    767px) and the inline layout in @media (min-width: 768px). Viewport width
    is fractional under browser zoom, and a width between 767 and 768
    matches neither query: the menu showed, the toggle showed beside it, and
    the toggle did nothing visible. Bootstrap hid .collapse unconditionally
    and only shows it from 768px up, which covers every width.

    So the hidden state of .navbar-collapse has to be a rule outside any
    max-width query, and no max-width query may decide whether the menu or
    the toggle is displayed: the min-width: 768px block alone overrides the
    base.
    """
    css_code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    targets = (".navbar-collapse", ".navbar-collapse.is-open", ".navbar-toggle")

    def capped(media):
        return any(re.search(r"max-width", prelude) for prelude in media)

    hidden_base = False
    for media, selector, body in css_rules(css_code):
        parts = [part.strip() for part in selector.split(",")]
        display = re.search(r"(?<![-\w])display\s*:\s*([^;]+)", body)
        if not display or not any(part in targets for part in parts):
            continue
        if capped(media):
            fail(
                "%s sets display inside %s. A width between two breakpoints "
                "(767.5px under browser zoom) matches neither that query nor "
                "min-width: 768px, and gets neither the hidden menu nor the "
                "inline one. Make the mobile state the base rule and let "
                "min-width: 768px override it." % (selector, " ".join(media))
            )
        if (
            ".navbar-collapse" in parts
            and not media
            and display.group(1).strip() == "none"
        ):
            hidden_base = True
    if not hidden_base:
        fail(
            "No unconditional `.navbar-collapse { display: none }` rule, so "
            "some width can show the mobile menu with no way to close it."
        )


def check_progress_bars(facts):
    """Bars animate from the CSS 5% default to data-percent."""
    if not facts.progress_bars:
        fail("No .progress-bar-line elements found in index.html.")

    for value, style in facts.progress_bars:
        if value is None:
            fail(
                "A .progress-bar-line has no data-percent, so main.js would "
                "set its width to 'undefined%'."
            )
        elif not value.isdigit() or int(value) > 100:
            fail("A .progress-bar-line has data-percent=%r, not an integer 0-100." % value)

        if style and "width" in style:
            fail(
                "A .progress-bar-line still hardcodes width in its style "
                "attribute (%r), which pins it at the final value." % style
            )


def check_card_handler(html, css):
    """Clicking Live Demo or Code must not also fire the card handler."""
    if "portfolio-card" not in html:
        return
    if "closest('a')" not in html and 'closest("a")' not in html:
        fail(
            "The portfolio card click handler does not bail out on anchor "
            "clicks, so clicking Live Demo or Code opens two tabs."
        )

    # The guard above is only reachable if the anchors are. .portfolio-overlay
    # covers the whole card at z-index 3 above the content's z-index 2, and an
    # opacity: 0 element is still hit-testable, so without pointer-events: none
    # every click lands on the overlay. That makes the Live Demo and Code links
    # dead and the anchor guard permanently false.
    #
    # Read out of css/style.css, not index.html: issue 20 moved the whole
    # portfolio block out of a JavaScript string in the page and into the
    # stylesheet. The handler this pairs with is still inline in index.html,
    # which is why this one check needs both files.
    rule = re.search(r"\.portfolio-overlay\s*\{(.*?)\}", css, re.S)
    if rule is None:
        fail("Could not find the .portfolio-overlay rule in css/style.css.")
    elif not re.search(r"pointer-events\s*:\s*none", rule.group(1)):
        fail(
            ".portfolio-overlay has no 'pointer-events: none', so it swallows "
            "every click on a card. The Live Demo and Code anchors are "
            "unreachable and the card handler's anchor guard never fires."
        )


def check_scroll_up_transition(css):
    """.scroll-up must not narrow the transition it inherits from .effect.

    <a class="scroll-up effect"> gets 'transition: all .4s' from .effect. A
    later, equal-specificity 'transition: opacity, visibility' on .scroll-up
    wins on source order and silently drops the hover background and color
    fade, so use 'all' and keep both.
    """
    rule = re.search(r"\.scroll-up\s*\{(.*?)\}", css, re.S)
    if rule is None:
        fail("Could not find the .scroll-up rule in css/style.css.")
        return

    declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", rule.group(1))
    if not declarations:
        return
    if not all(value.strip().startswith("all") for value in declarations):
        fail(
            ".scroll-up declares a transition that does not use 'all', which "
            "overrides .effect's 'transition: all .4s' and kills the hover "
            "fade. Declared: %s" % "; ".join(v.strip() for v in declarations)
        )


def check_no_dead_code(facts, js):
    """Nothing in main.js may target an element or library the page lacks."""
    banned = [
        ("magnificPopup", "no .popup-youtube or .popup-link element exists"),
        ("owlCarousel", "no .home-carousel or .testimonial-slider element exists"),
        ("isotope", "no '#work .filtr-container' element exists"),
        ("imagesLoaded", "only the deleted isotope block used it"),
        ("particlesJS", "index.html never loads js/particles.js"),
        ("typer", "the typer initialization was deleted"),
        ("scrollSpeed", "the mousewheel hijack was removed; it overrode native scrolling"),
        ("mousewheel", "the mousewheel hijack was removed; it overrode native scrolling"),
        ("parallax", "the hero uses background-size: cover, so moving backgroundPosition exposes blank space"),
        ("progress-cont", "no .progress-cont span exists in the markup"),
        # Issue 31: no library provides any of these any more.
        ("jQuery", "jQuery was retired in issue 31 and no page loads it"),
        ("$(", "jQuery was retired in issue 31 and no page loads it"),
        ("$.", "jQuery was retired in issue 31 and no page loads it"),
        (".collapse(", "Bootstrap's collapse plugin was retired in issue 31"),
        (".animate(", "jQuery's .animate() was retired in issue 31; scrolling is native"),
        (".fadeOut(", "jQuery's .fadeOut() was retired in issue 31"),
    ]
    for token, reason in banned:
        if token in js:
            fail("js/main.js still references %r: %s." % (token, reason))

    if facts.parallax:
        fail(
            "index.html still puts the parallax class on <%s>, but nothing "
            "implements it." % ">, <".join(facts.parallax)
        )


def check_syntax():
    """Optional: node is a convenience here, never a project dependency."""
    if shutil.which("node") is None:
        print("skip: node not found, cannot syntax-check js/main.js")
        return
    result = subprocess.run(
        ["node", "--check", str(MAIN_JS)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail("js/main.js is not valid JavaScript:\n%s" % result.stderr.strip())


def main():
    html = INDEX.read_text(encoding="utf-8")
    js = MAIN_JS.read_text(encoding="utf-8")
    css = STYLE_CSS.read_text(encoding="utf-8")

    facts = IndexFacts()
    facts.feed(html)

    check_script_tag(facts)
    check_nav_toggle(facts)
    check_native_smooth_scroll(css, js)
    check_deep_link_is_not_animated(css, js)
    check_collapse_covers_every_width(css)
    check_smooth_scroll_starts_on_load(css, js)
    check_nav_breakpoints(css)
    check_nav_targets(facts)
    check_link_targets_take_focus(facts, css, js)
    check_progress_bars(facts)
    check_card_handler(html, css)
    check_scroll_up_transition(css)
    check_no_dead_code(facts, js)
    check_syntax()

    if failures:
        print("FAIL: %d check(s) failed\n" % len(failures))
        for message in failures:
            print("  - %s" % message)
        return 1

    print("PASS: site interactivity is wired up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
