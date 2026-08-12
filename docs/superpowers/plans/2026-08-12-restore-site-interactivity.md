# Restore Site Interactivity (issue #16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load `js/main.js` on `index.html` and make every interaction it defines actually work, after stripping it down to the code that has a matching element in the markup.

**Architecture:** `js/main.js` shrinks from 664 lines to roughly 130 by deleting the blocks that target elements no page contains (magnific-popup, owl carousel, isotope/imagesLoaded, particles, the commented-out typer and AJAX contact form) and the `jQuery.scrollSpeed` mousewheel hijack. What remains is one scroll handler that drives sticky nav, active-link tracking, and skill bars, plus click handlers for anchor scrolling, scroll-to-top, and mobile nav collapse. `index.html` gets the script tag back plus three markup fixes. Because the repo has no test runner, the automated gate is a new standard-library Python checker, `tools/verify_interactivity.py`, that asserts the wiring invariants statically; behavior is proven by a browser drive in Phase 6.

**Tech Stack:** Vanilla HTML5/CSS3, jQuery 2.2.4, Bootstrap 3. No build step, no package manager, no CI. Python 3 standard library for the checker.

## Global Constraints

- No emojis anywhere: code, comments, commit messages, PR text.
- No em dashes (`-`-style long dash) anywhere. Use commas, periods, or colons.
- JavaScript only, never TypeScript.
- No build system. `tools/` holds standalone scripts run by hand, never a build step.
- Do not reintroduce a library without an element that actually uses it.
- Do not run `git commit` or `git push`. This project grants no git exception, so the run stops before Phase 9 and hands the commands to the user.
- Target the `main` branch as it actually is. The untracked `CLAUDE.md` describes the unmerged issue #15 branch (hero WebP variants, `tools/verify_assets.py`, removed libraries); none of that exists here.

## Decisions already approved

| Question | Decision |
|---|---|
| Hero parallax | Drop it. Delete `parallax()` from `main.js` and the `parallax` class from `index.html:87`. `.home-1` uses `background-size: cover`, so shifting `backgroundPosition` slides the image down and exposes blank space under the dark overlay. |
| Smooth scroll | Delete `jQuery.scrollSpeed` (the mousewheel override). Keep the jQuery anchor animation so `data-speed` still applies. Do **not** add CSS `scroll-behavior: smooth`; it fights `animate()`. |
| Skill bar no-JS fallback | Accept the gap. `data-percent` drives the width; with JS off the bars sit at the 5% CSS default. The portfolio section already hard-requires JS. |

## File Structure

| File | Responsibility |
|---|---|
| Create `tools/verify_interactivity.py` | Standalone checker for the wiring invariants. Standard library only, exits non-zero with a reason per failure. |
| Rewrite `js/main.js` | The only site-wide behavior file. Every block must have a matching element in `index.html`. |
| Modify `index.html` | Add the `main.js` tag, `one-page-section` on `#portfolio`, `data-percent` on the three skill bars, drop the `parallax` class, guard the portfolio card click handler. |
| Modify `css/style.css:1199-1226` | Make `.scroll-up` genuinely hidden rather than just transparent. |
| Modify `CLAUDE.md` | Delete the "js/main.js is not loaded" warning and correct the line references it anchors. |

---

### Task 1: Verification checker (red)

Write the gate first and watch it fail against the current tree. Every check maps to an acceptance criterion or a defect named in issue #16.

**Files:**
- Create: `tools/verify_interactivity.py`

**Interfaces:**
- Produces: a CLI gate, `python3 tools/verify_interactivity.py`, exit 0 on pass and 1 on failure. Later tasks are complete when it exits 0.

- [ ] **Step 1: Write the checker**

```python
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

import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
MAIN_JS = ROOT / "js" / "main.js"

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

    facts = IndexFacts()
    facts.feed(html)

    check_script_tag(facts)
    check_nav_targets(facts)
    check_progress_bars(facts)
    check_card_handler(html)
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
```

- [ ] **Step 2: Run it against the untouched tree to verify it fails**

Run: `python3 tools/verify_interactivity.py; echo "exit=$?"`

Expected: `exit=1`, with failures naming at least the missing `main.js` tag, `#portfolio` lacking `one-page-section`, three skill bars with no `data-percent` and a hardcoded `width`, the unguarded card handler, the `parallax` class on `<section>`, and the `magnificPopup` / `owlCarousel` / `isotope` / `particlesJS` / `scrollSpeed` / `mousewheel` / `parallax` / `progress-cont` references in `js/main.js`.

If any of those do **not** appear, the check is wrong, not the tree. Fix the checker before moving on.

---

### Task 2: Rewrite js/main.js (green, JavaScript side)

**Files:**
- Rewrite: `js/main.js` (currently 664 lines)

**Interfaces:**
- Consumes: jQuery 2.2.4 and the Bootstrap 3 collapse plugin, both already loaded by `index.html`.
- Produces: the DOM contract Task 3 must satisfy: an element per nav `href` carrying `one-page-section`, `.progress-bar-line[data-percent]`, `.skills-section`, `.scroll-up`, `.nav-wrapper`, `a.scroll`.

- [ ] **Step 1: Replace the whole file**

```javascript
/*=========================================================================

  Site behavior for GeoBrad.dev.

  Loaded by index.html only. resume.html and privacy.html are standalone.

  Every block below has a matching element in index.html. Adding code here
  that targets an element the markup does not contain recreates issue #16,
  where 664 lines sat dead in the tree for two years.

=========================================================================*/

$(function () {
    "use strict";

    var allWindow = $(window),
        navBar = $(".nav-wrapper"),
        scrollUp = $(".scroll-up"),
        navList = navBar.find("ul.navbar-nav"),
        sections = $(".one-page-section"),
        skillsSection = $(".skills-section"),
        skillLines = $(".progress-bar-line"),
        motionQuery = window.matchMedia
            ? window.matchMedia("(prefers-reduced-motion: reduce)")
            : null,
        scrollPos = 0;

    // The navbar is position: fixed, so anything that scrolls to a section
    // has to clear it or the heading lands underneath.
    function navHeight() {
        return navBar.outerHeight() || 0;
    }

    // Honor the OS setting rather than animating over someone who asked us
    // not to. Read at call time, not at load, since the setting can change.
    function duration(speed) {
        return motionQuery && motionQuery.matches ? 0 : speed;
    }

/*------------------------------------------------
  Preloader
--------------------------------------------------*/

    allWindow.on("load", function () {
        $(".loader-con").fadeOut("slow");
    });

/*------------------------------------------------
  Sticky navigation and scroll-to-top visibility
--------------------------------------------------*/

    function stickyNav() {
        navBar.toggleClass("nav-sticky", scrollPos >= 100);
        scrollUp.toggleClass("show-up-btn", scrollPos >= 1000);
    }

/*------------------------------------------------
  Smooth scrolling for on-page anchors
--------------------------------------------------*/

    $("a.scroll").on("click", function (event) {
        if (location.pathname.replace(/^\//, "") !== this.pathname.replace(/^\//, "") ||
            location.hostname !== this.hostname) {
            return;
        }

        var target = $(this.hash);
        if (!target.length) {
            target = $("[name=" + this.hash.slice(1) + "]");
        }
        if (!target.length) {
            return;
        }

        event.preventDefault();
        $("html, body").animate({
            scrollTop: Math.max(0, target.offset().top - navHeight())
        }, duration($(this).data("speed") || 800));
    });

    scrollUp.on("click", function (event) {
        event.preventDefault();
        $("html, body").animate({ scrollTop: 0 }, duration(900));
    });

/*------------------------------------------------
  Close the mobile dropdown after tapping a link
--------------------------------------------------*/

    // Bootstrap 3 returns early from hide() when the element lacks .in, so
    // this is a no-op on desktop where CSS keeps the menu expanded.
    navBar.find(".navbar-collapse a").on("click", function () {
        navBar.find(".navbar-collapse").collapse("hide");
    });

/*------------------------------------------------
  Highlight the nav link for the visible section
--------------------------------------------------*/

    function changeActiveNavLink() {
        var probe = scrollPos + navHeight();

        sections.each(function () {
            var section = $(this),
                sectionTop = section.offset().top;

            if (probe < sectionTop || probe > sectionTop + section.height()) {
                return;
            }

            navList.find("a").removeClass("active");
            navList.find('[href="#' + section.attr("id") + '"]').addClass("active");
        });
    }

/*------------------------------------------------
  Skill bars, animated once when scrolled into view
--------------------------------------------------*/

    function progressBars() {
        if (!skillsSection.length || skillsSection.hasClass("done")) {
            return;
        }

        var trigger = skillsSection.offset().top - (allWindow.height() - 160);
        if (scrollPos < trigger) {
            return;
        }

        skillsSection.addClass("done");
        skillLines.each(function () {
            var line = $(this),
                percent = parseInt(line.attr("data-percent"), 10);

            if (!isNaN(percent)) {
                line.css("width", percent + "%");
            }
        });
    }

/*------------------------------------------------
  One scroll handler drives all three
--------------------------------------------------*/

    function scrollFunctions() {
        scrollPos = allWindow.scrollTop();
        stickyNav();
        changeActiveNavLink();
        progressBars();
    }

    allWindow.on("scroll", scrollFunctions);

    // Run once so a reload partway down the page, or a deep link, starts in
    // the right state instead of waiting for the first scroll event.
    scrollFunctions();

});
```

- [ ] **Step 2: Syntax-check it**

Run: `node --check js/main.js && echo OK`
Expected: `OK`

- [ ] **Step 3: Run the checker**

Run: `python3 tools/verify_interactivity.py; echo "exit=$?"`

Expected: still `exit=1`, but every `js/main.js still references ...` failure is gone. The remaining failures are all `index.html` ones, which Task 3 fixes.

---

### Task 3: Wire up index.html (green, markup side)

**Files:**
- Modify: `index.html:87` (drop `parallax`), `index.html:190,200,210` (skill bars), `index.html:325` (`#portfolio`), `index.html:467-468` (script tag), `index.html:561-570` (card handler)

**Interfaces:**
- Consumes: the DOM contract from Task 2.

- [ ] **Step 1: Drop the parallax class from the hero**

`index.html:87`, from:

```html
<section id="home" class="home-1 parallax one-page-section">
```

to:

```html
<section id="home" class="home-1 one-page-section">
```

- [ ] **Step 2: Give the three skill bars a data-percent and remove the inline width**

`index.html:190`, from `<div class="progress-bar-line main-color-bg" style="width: 90%;"></div>`
to `<div class="progress-bar-line main-color-bg" data-percent="90"></div>`

`index.html:200`, from `<div class="progress-bar-line main-color-bg" style="width: 75%;"></div>`
to `<div class="progress-bar-line main-color-bg" data-percent="75"></div>`

`index.html:210`, from `<div class="progress-bar-line main-color-bg" style="width: 75%;"></div>`
to `<div class="progress-bar-line main-color-bg" data-percent="75"></div>`

- [ ] **Step 3: Let the portfolio section take part in nav highlighting**

`index.html:325`, from:

```html
<section id="portfolio" class="section">
```

to:

```html
<section id="portfolio" class="section one-page-section">
```

- [ ] **Step 4: Load main.js**

`index.html:467`, after the isotope tag and before the inline `<script>`:

```html
<!-- jQuery Filterizr JS -->
<script src="js/isotope.pkgd.min.js"></script>
<!-- Site behavior -->
<script src="js/main.js"></script>
<!-- Custom js -->
<script>
```

- [ ] **Step 5: Stop the card handler from opening a second tab**

`index.html:561-570`, from:

```javascript
            // Add click handlers for the cards
            document.querySelectorAll('.portfolio-card').forEach((card, index) => {
                const repo = portfolioRepos[index];
                card.addEventListener('click', () => {
                    if (repo.homepage) {
                        window.open(repo.homepage, '_blank');
                    } else {
                        window.open(repo.html_url, '_blank');
                    }
                });
            });
```

to:

```javascript
            // Make the whole card clickable, but let the real anchors inside
            // it handle their own clicks. Without the guard, clicking "Live
            // Demo" or "Code" opens the link and then bubbles up here, which
            // opens a second tab.
            document.querySelectorAll('.portfolio-card').forEach((card, index) => {
                const repo = portfolioRepos[index];
                card.addEventListener('click', (event) => {
                    if (event.target.closest('a')) return;
                    window.open(repo.homepage || repo.html_url, '_blank', 'noopener');
                });
            });
```

- [ ] **Step 6: Run the checker**

Run: `python3 tools/verify_interactivity.py; echo "exit=$?"`
Expected: `PASS: site interactivity is wired up` and `exit=0`.

---

### Task 4: Make the scroll-to-top button genuinely hidden

`.scroll-up` is `opacity: 0` with no `pointer-events` or `visibility`, so it is an invisible but clickable and tab-focusable target parked in the bottom-right corner at all times. The acceptance criterion is "the scroll-to-top button appears and works"; a button that is always clickable but never visible does not meet it.

**Files:**
- Modify: `css/style.css:1199-1226`

- [ ] **Step 1: Hide it properly and transition it in**

`css/style.css:1199`, from:

```css
.scroll-up {
    position: fixed;
    font-size: 28px;
    width: 46px;
    height: 46px;
    text-align: center;
    line-height: 38px;
    color: #fafafa;
    border: 2px solid #333;
    background-color: #333;
    bottom: 25px;
    right: 30px;
    opacity: 0;
    z-index: 60;
}
```

to:

```css
.scroll-up {
    position: fixed;
    font-size: 28px;
    width: 46px;
    height: 46px;
    text-align: center;
    line-height: 38px;
    color: #fafafa;
    border: 2px solid #333;
    background-color: #333;
    bottom: 25px;
    right: 30px;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    -webkit-transition: opacity .3s ease, visibility .3s ease;
    -o-transition: opacity .3s ease, visibility .3s ease;
    -moz-transition: opacity .3s ease, visibility .3s ease;
    transition: opacity .3s ease, visibility .3s ease;
    z-index: 60;
}
```

`css/style.css:1224`, from:

```css
.show-up-btn {
    opacity: 1;
}
```

to:

```css
.show-up-btn {
    opacity: 1;
    visibility: visible;
    pointer-events: auto;
}
```

- [ ] **Step 2: Confirm nothing else regressed**

Run: `python3 tools/verify_interactivity.py; echo "exit=$?"`
Expected: `exit=0`.

---

### Task 5: Reconcile CLAUDE.md

`CLAUDE.md` carries a standing warning that `js/main.js` is not loaded. That becomes false the moment Task 3 lands, and the line numbers it cites all move.

**Files:**
- Modify: `CLAUDE.md`

Note: `CLAUDE.md` is currently untracked because `.gitignore:120` (`/C*.md`) matches it. That is issue #23 and is out of scope here. Edit the file regardless; whether it can be committed is issue #23's problem, and the PR body should say so.

- [ ] **Step 1: Delete the "js/main.js is not loaded" section**

Remove the whole `### js/main.js is not loaded` block, including the sentence pointing at issue #16.

- [ ] **Step 2: Replace it with what is true now**

```markdown
### js/main.js

Loaded by `index.html` only; `resume.html` and `privacy.html` are standalone.
It drives the sticky navbar, on-page smooth scrolling, active-link tracking,
mobile nav collapse, the scroll-to-top button, and the skill bars.

Everything in it has a matching element in `index.html`. That is the rule the
file exists to keep: it once held 664 lines, of which roughly 500 targeted
elements no page contained, and the whole file went unloaded for two years
without anyone noticing (issue #16). Do not add a block here without an
element that uses it, and run `python3 tools/verify_interactivity.py` after
touching `js/main.js` or the markup it depends on.

Skill bar widths come from `data-percent` on `.progress-bar-line`, not from
inline styles. CSS starts the bars at 5% (`css/style.css:716`) and JavaScript
animates them to the target once the section scrolls into view. With
JavaScript disabled the bars stay at 5%; that is accepted, since the portfolio
section already requires JavaScript.

The hero has no parallax. `.home-1` uses `background-size: cover`, so shifting
`backgroundPosition` slides the image down and exposes blank space under the
overlay. The old `parallax()` function and the `parallax` class were removed
together.
```

- [ ] **Step 3: Add the checker to the Development Workflow section**

Under "Testing Locally", add:

```markdown
### Verifying site interactivity

```bash
python3 tools/verify_interactivity.py
```

Exits 0 when the issue #16 wiring still holds: `index.html` loads `js/main.js`
after jQuery, every section a nav link points at carries `one-page-section`,
every skill bar has a `data-percent` and no inline width, the portfolio card
click handler yields to real anchors, and `js/main.js` references nothing the
markup lacks. Standard library only; it syntax-checks `js/main.js` with `node`
when node happens to be installed, and skips that check otherwise. Run it
after touching `js/main.js`, `index.html`, or the nav markup.
```

- [ ] **Step 4: Fix the stale line references elsewhere in CLAUDE.md**

The "Site Structure" and "Key Features & Architecture" sections cite
`js/main.js:140-157`, `:159-184`, `:212-236`, `:61-132`, `:246-268`,
`:278-304`, `:321-411`. All of those are wrong after Task 2. Replace them with
function names rather than line numbers, since line numbers go stale:
`stickyNav()`, the `a.scroll` click handler, `changeActiveNavLink()`,
`progressBars()`. Delete the parallax and commented-out-contact-form bullets;
neither exists anymore.

---

## Verification

Automated, run from the repo root:

```bash
python3 tools/verify_interactivity.py   # expect: PASS, exit 0
node --check js/main.js                 # expect: silent, exit 0
```

Live drive (Phase 6, High tier, so failure and edge paths too). Serve the site
and exercise every acceptance criterion in a real browser:

```bash
python3 -m http.server 8765
```

| Criterion | How to prove it |
|---|---|
| Navbar goes sticky past 100px | Load at top, confirm `.nav-wrapper` has no `nav-sticky`. Scroll to 150, confirm it does and the background turns white. Scroll back to 50, confirm it comes off. |
| Nav links smooth-scroll | Click each of HOME, ABOUT, SERVICES, PORTFOLIO, CONTACT. Confirm `scrollY` animates rather than jumping, and the section heading lands below the navbar, not under it. |
| `data-speed` still honored | CONTACT (1700ms) visibly takes longer than HOME (800ms). |
| Active link tracks the section, including PORTFOLIO | Scroll through the page and confirm `.active` moves across all five links, PORTFOLIO included. |
| Mobile nav closes after tapping | Resize to 375px wide, open the toggle, tap ABOUT, confirm `.navbar-collapse` loses `.in`. |
| Scroll-to-top appears and works | Below 1000px of scroll, confirm `.scroll-up` has no `show-up-btn` and `elementFromPoint` at its corner is not the button. Past 1000, confirm it is visible, then click it and confirm `scrollY` returns to 0. |
| Skill bars animate | Load at top, confirm the three bars read 5%. Scroll to About, confirm they settle at 90%, 75%, 75%. |
| Card opens exactly one tab | Patch `window.open` to count calls. Click a card body: 1 call. Click "Code": 0 `window.open` calls, the anchor handles it. Click "Live Demo" where present: same. |
| No console errors | Collect console messages across the whole drive. Expect zero errors. A GitHub API rate-limit message is a network condition, not a regression; note it if it appears. |
| Failure path: GitHub API down | Block `api.github.com`, reload, confirm the loader still hides, the error copy renders, and nav, sticky, skill bars, and scroll-to-top all still work. This matters because the loader is hidden by the portfolio script's `finally`, not by `main.js`. |
| Edge path: reduced motion | Emulate `prefers-reduced-motion: reduce`, click a nav link, confirm it jumps instantly instead of animating. |
| Edge path: deep link | Load `index.html#contact` directly, confirm the navbar is already sticky and CONTACT is already active without needing a scroll event. |
