#!/usr/bin/env python3
"""Verify the site's interactive JavaScript is actually wired up.

Standalone, standard library only, run by hand from the repo root:

    python3 tools/verify_interactivity.py

Exits 0 when the issue #16 acceptance criteria still hold at the source
level: index.html loads js/main.js after jQuery, every section a nav link
points at takes part in active-link tracking, every skill bar carries a
data-percent instead of a hardcoded inline width, the portfolio card click
handler yields to real anchors, and js/main.js references nothing the
markup does not contain.

Behavior (does the navbar actually go sticky, does the bar actually
animate) cannot be checked here. Drive that in a browser.
"""

import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
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


def check_script_tag(facts):
    """main.js has to load, and it has to load after jQuery."""
    if "js/main.js" not in facts.scripts:
        fail(
            "index.html does not load js/main.js. The tag was dropped in "
            "eba0f7b and every interaction in that file died with it."
        )
        return

    jquery = [i for i, src in enumerate(facts.scripts) if "jquery.min.js" in src]
    if not jquery:
        fail("index.html loads js/main.js but not jQuery; main.js is jQuery code.")
    elif facts.scripts.index("js/main.js") < jquery[0]:
        fail("js/main.js is loaded before jQuery, so it throws on load.")


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


def check_card_handler(html):
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
    rule = re.search(r"\.portfolio-overlay\s*\{(.*?)\}", html, re.S)
    if rule is None:
        fail("Could not find the .portfolio-overlay rule in index.html.")
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
    check_nav_targets(facts)
    check_progress_bars(facts)
    check_card_handler(html)
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
