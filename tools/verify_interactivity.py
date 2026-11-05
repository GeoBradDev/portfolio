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
    if "js/main.js" not in facts.scripts:
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
    allowed = media_blocks(css_code, r"prefers-reduced-motion\s*:\s*no-preference")
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

    margin = [
        m for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_code)
        if any(part.strip() == ".one-page-section" for part in m.group(1).split(","))
        and re.search(r"scroll-margin-top\s*:", m.group(2))
    ]
    if not margin:
        fail(
            ".one-page-section declares no scroll-margin-top, so a nav link "
            "lands the section heading under the fixed header."
        )

    js_code = re.sub(r"/\*.*?\*/|//[^\n]*", "", js, flags=re.S)
    for token, reason in (
        ("scrollTo(", "scrolling is native now"),
        ("scrollBy(", "scrolling is native now"),
        ("scrollIntoView(", "scrolling is native now"),
        ("scrollTop =", "assigning scrollTop is a scripted scroll; scrolling is native now"),
        ("preventDefault", "cancelling a click stops the native fragment navigation and its hash update"),
    ):
        if token in js_code:
            fail("js/main.js contains %r: %s." % (token, reason))


def check_nav_targets(facts):
    """ChangeClass() only sees sections carrying one-page-section."""
    for target in facts.nav_targets:
        classes = facts.ids.get(target)
        if classes is None:
            fail("A nav link points at #%s but no element has that id." % target)
        elif "one-page-section" not in classes:
            fail(
                "#%s lacks the one-page-section class, so its nav link never "
                "highlights." % target
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
    check_nav_targets(facts)
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
