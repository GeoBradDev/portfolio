# Plan: Bootstrap 3.4.1 and Font Awesome 4.7.0 are end of life; jQuery 3.x is pinned by them (issue #31)

Risk tier: High. Not forced by a category, but it raises on every count: stateful UI
(mobile toggle, sticky nav, active link, skill bars, loader) that no unit test exercises, it
alters existing behavior rather than adding, it is scroll and animation driven, and it
touches more than a dozen files including every verifier but one. Testability, not size, is
what puts it at High: the only real proof is a browser at two widths.

Domain skills:
- superpowers:test-driven-development: invoke. Every verifier change is written and run red
  before the markup, CSS, or JS that turns it green.
- superpowers:verification-before-completion: invoke before any success claim.
- frontend-design:frontend-design: not applicable because the bar is visual parity with the
  current site, not a new design.
- chrome-devtools-mcp:* (a11y-debugging, debug-optimize-lcp, chrome-devtools): not
  applicable because the MCP server failed to connect this session; the same evidence comes
  from Lighthouse 12 on the CLI and a Playwright script in a scratch virtualenv.
- django, django-ninja-api, python-fastapi, vercel-react-*, expo:*: not applicable because
  this is a static HTML, CSS, and vanilla JavaScript site.

Owner decisions, already made: no framework. Vanilla `js/main.js`; CSS grid and flex rules in
`css/style.css` in place of the Bootstrap 3 grid and utilities, with a local `.sr-only`; inline
SVG icons in place of Font Awesome 4.7 on `index.html` and `resume.html`; the mobile toggle is
a hand-written `<button aria-expanded>`. No third-party runtime library remains.

## Acceptance criteria

From the issue, verbatim:

1. No page loads Bootstrap 3.x, Font Awesome 4.x, or jQuery 3.x. Any remaining third-party
   library is on a release line its maintainers currently support.
2. Mobile nav toggle, smooth scroll, active-link highlighting, sticky nav, back-to-top, and
   skill bars behave as they do today at 375px and 1440px.
3. All six `tools/verify_*.py` scripts pass, updated where they assert the old versions.
4. Homepage JavaScript weight drops by at least 100 KB uncompressed.
5. Lighthouse accessibility and SEO stay at 100 on `index.html`.

Made checkable for this run:

- C1a. No file in the tree is named or referenced as `jquery`, `bootstrap`, `font-awesome`,
  `fontawesome`, or `glyphicons`, except as a removed-asset entry or prose in a verifier or
  CLAUDE.md. `js/jquery.min.js`, `js/bootstrap.min.js`, `css/bootstrap.min.css`,
  `css/font-awesome.min.css`, and every file in `fonts/` are deleted (the directory holds
  nothing else). Every `<script src>` on every page is first-party (today: `js/main.js`
  only), and every stylesheet link is `css/style.css` or Google Fonts (a font, not a runtime
  library).
- C1b. No page or the inline renderer uses a Bootstrap grid or utility class
  (`col-xs|sm|md|lg-*`, `col-*-offset-*`, `row`, `text-muted`, `navbar-right`, `collapse`,
  `data-toggle`, `data-target`) or a Font Awesome class (`fa`, `fa-*`). Class names that are
  the site's own and keep a local rule (`container`, `sr-only`, `text-center`, `nav`,
  `navbar-*` names the site already styles) may stay.
- C1c. Every inline `<svg>` on every page, and every SVG the renderer creates, carries
  `aria-hidden="true"` and `focusable="false"`. Every icon-only control keeps its
  `aria-label`. The Bluesky `<img alt="Bluesky">` links stay as they are.
- C2a. At 375x812 and 1440x900, full-page screenshots of `index.html` in four states (top of
  page; scrolled to the services section so the nav is sticky; scrolled past 1000px so the
  back-to-top button shows; skill bars animated) match the baseline captured from
  `origin/main` before any change, with every remaining pixel difference listed and
  explained (icon anti-aliasing is acceptable; any element moving is not). At 375 also the
  menu-open state. `resume.html` in light and dark at both widths likewise.
- C2b. Measured before and after, at both widths, and equal within 1px: `#contact-form`
  height (387.5px at 1440 today), collapsed sticky header height, open mobile header height,
  the y of every section's top, each skill bar's final width.
- C2c. Behaviors, driven in a real browser at both widths: the toggle (375 only; hidden at
  1440) opens and closes the menu and flips `aria-expanded`; tapping a menu link closes it;
  each nav link and the hero chevron land the section top at the bottom edge of the sticky
  header (within 1px), including when activated with the 375 menu open; scrolling past 100px
  adds `.nav-sticky` and back past removes it; past 1000px shows `.scroll-up`, and activating
  it returns to y=0; the active nav link tracks the visible section in both scroll
  directions; the skill bars sit at 5% until the skills section scrolls into view, then reach
  their `data-percent`; the loader fades out after `load`. Under
  `prefers-reduced-motion: reduce`, nav links and back-to-top jump with no animation.
- C3. The six verifiers exit 0, and each removed old-stack check has a named replacement that
  enforces the new stack (Order of work lists the mapping). `check_ci_workflow` still passes.
- C4. Sum of uncompressed bytes of every script the homepage executes (external files plus
  inline `<script>` bodies, JSON-LD excluded), before and after; the drop is at least
  102400 bytes. Both numbers go in the PR.
- C5. Lighthouse 12 accessibility and SEO both 100 on `index.html`; accessibility on
  `resume.html` in light and dark (dark via `--emulated-media`-equivalent or by toggling the
  stored preference) does not drop below the baseline captured before the change.

## Files that change

- `index.html`: drop the `bootstrap.min.css`, `font-awesome.min.css`, `jquery.min.js`, and
  `bootstrap.min.js` tags; add one hidden SVG sprite (`<svg aria-hidden="true"
  style="display:none">` of `<symbol id="icon-*">`) right after `<body>`'s skip link and
  loader; replace every `<i class="fa ...">` with `<svg class="icon icon-NAME"
  aria-hidden="true" focusable="false"><use href="#icon-NAME"></use></svg>`; replace grid
  classes with the site's own layout classes; rewrite the nav toggle as a plain
  `<button type="button" class="navbar-toggle" aria-expanded="false" aria-controls="bm-navbar">`;
  drop `class="collapse"` and the `data-speed` attributes (nothing reads them once scrolling is
  native); in the inline renderer, replace `el("i", "fa fa-star")` and friends with an
  `icon(name)` helper built with `document.createElementNS`, and replace `col-*`,
  `text-muted` in its `innerHTML` strings and `className`s. Update the comments that name
  Bootstrap or Font Awesome (the `.sr-only` one in the form, the star-glyph one in the
  renderer, the social-list one).
- `resume.html`: drop the `font-awesome.min.css` link; add its own sprite of the 11 glyphs it
  uses; replace each `<i class="fa ...">`; adjust `.icon` in its inline `<style>` so the SVG
  sizes, colors (`fill: currentColor`), and aligns like the glyph did in both themes.
- `css/style.css`: a new base section at the top replacing what `bootstrap.min.css` supplied
  that the site actually renders (see Order of work, task 3); local `.container`, `.sr-only`,
  `.text-center`, layout rules per section; the nav and toggle rules; native smooth scroll;
  the `.icon` sizing rule; drop the `a:focus:not(:focus-visible)` rule (see Risks); drop the
  `!important` flags on `#github-projects` and `.portfolio-item` that only existed to beat
  Bootstrap, and rewrite the comment above them.
- `js/main.js`: full vanilla rewrite.
- Deleted: `js/jquery.min.js`, `js/bootstrap.min.js`, `css/bootstrap.min.css`,
  `css/font-awesome.min.css`, `fonts/FontAwesome.otf`, `fonts/fontawesome-webfont.{eot,svg,ttf,woff,woff2}`,
  `fonts/glyphicons-halflings-regular.{eot,svg,ttf,woff,woff2}`.
- `tools/verify_assets.py`, `tools/verify_security.py`, `tools/verify_content.py`,
  `tools/verify_interactivity.py`, `tools/verify_seo_a11y.py`: see task mapping.
  `tools/verify_portfolio.py`: docstring only (it names Font Awesome glyphs).
- `CLAUDE.md`: reconciled in Phase 8 by the coordinator, not by the implementer.
- This plan.

Not changed: `privacy.html`, and `thanks.html` and `404.html` apart from one CSS comment each
(none loads any of the three libraries, but each comment said the page avoided "pulling in
bootstrap.min.css and style.css", and `verify_assets` rejects a page that names a dead asset
outside an HTML comment; found by task 4's red run), `.github/workflows/verify.yml`, `projects.json`, `tools/build_projects.py`, the
emoji glyphs on `resume.html`'s theme toggle (out of scope, as `verify_portfolio.py` already
documents), the dead `#particles-js`/`.owl-*`/`.mfp-*` CSS (out of scope, CLAUDE.md says no
issue covers it), the loader's behavior (issue #32).

## Order of work

Each task: change the verifier first, run it and record the red output, then change the
site, run all six, commit. Commits are Conventional and end with the Co-Authored-By line.

### Task 0: Baseline (no repo change, no commit)

Before touching anything, from a pristine checkout of `origin/main` (a `git worktree add
--detach` in the scratch directory, served on its own port):

1. Scratch virtualenv: `python3 -m venv <scratch>/venv && <scratch>/venv/bin/pip install
   playwright`, using the Chromium already in `~/.cache/ms-playwright` (chromium-1248) or
   `/usr/bin/google-chrome` via `channel`/`executable_path`. Nothing is added to the repo.
2. A drive script in scratch, `drive.py`, parameterized by base URL, that for each width
   (375x812, 1440x900) disables the loader's influence by waiting for it to reach
   `display: none`, freezes CSS transitions for screenshots only
   (`*{transition:none!important;animation:none!important}` injected for the screenshot
   pass, never for the behavior pass), waits for `#github-projects .portfolio-item`, and
   records the C2a screenshots and the C2b metrics as JSON. The same script runs the C2c
   behavior pass and prints one PASS or FAIL line per behavior. It must run unchanged
   against the baseline and against the branch, so the baseline also proves the script.
3. Lighthouse 12 baseline on `index.html` (accessibility, SEO) and `resume.html`
   (accessibility, light and dark), and the C4 byte count on the baseline.
4. Save all of it under `<scratch>/baseline/` and report the paths.

### Task 1: Icons to inline SVG

Red first:
- `verify_seo_a11y.py`, `AccessibleNames`: replace the `<i class="fa">` aria-hidden rule with
  two: any `<i>` or `<span>` carrying a `fa` or `fa-*` class is a failure (Font Awesome is
  gone, so such an element renders nothing), and every `<svg>` must carry
  `aria-hidden="true"` and `focusable="false"`. The rest of the class (accessible names from
  aria-label, text, img alt; the unclosed-frame `finish()`) is untouched. Add a check that the
  inline renderer in `index.html` builds icons with `createElementNS` and sets `aria-hidden`
  on what it creates (the static parser never sees renderer output). Update the docstring.
- `verify_security.py`: replace `check_font_awesome_is_single_local_version` with
  `check_icons_are_inline_svg`: no page links any `font-awesome` stylesheet or loads from
  `cdnjs.cloudflare.com`; no page or the renderer uses an `fa`, `fa-*`, `fas`, `fab`, `far`,
  `fal` class; every `<use href="#icon-X">` on a page resolves to a `<symbol id="icon-X">` on
  the same page (a missing symbol renders an empty box with no error anywhere), and the same
  for every icon name the renderer asks for.
- `verify_content.py`: drop the `fontawesome` entry from `FONT_FAMILIES_FROM` and make the
  dict empty but kept, with its docstring sentence rewritten to name no stylesheet that no
  longer exists.

Then the site:
- Generate the symbols from `fonts/fontawesome-webfont.svg` (still in the tree at this point)
  with a one-off script in scratch, not committed. That file is an SVG font: each
  `<glyph glyph-name="..." unicode="..." horiz-adv-x="W" d="...">` is in font units, 1792 per
  em, y up, ascent 1536, descent 256. Emit each symbol as
  `<symbol id="icon-NAME" viewBox="0 0 W 1792"><path transform="matrix(1 0 0 -1 0 1536)" d="..."/></symbol>`
  (W defaults to 1536 when the glyph omits it, per the font's `horiz-adv-x`). Map Font Awesome
  class to glyph name from `css/font-awesome.min.css` (`.fa-NAME:before{content:"\fXXX"}`) to
  the glyph's `unicode`. Glyphs needed. index.html: envelope, map-marker, phone, github,
  facebook, youtube, instagram, linkedin, globe, code, database, cogs, line-chart, heart,
  angle-up; renderer: star, external-link, github. resume.html: envelope, phone, linkedin,
  github, map-marker, user, code, briefcase, graduation-cap, certificate, file-pdf-o.
  Because the paths are Font Awesome 4.7's own outlines, the shapes are pixel-identical.
  Attribution: Font Awesome 4.7.0 by Dave Gandy, font under SIL OFL 1.1; put a one-line
  comment above each sprite saying so, and that the outlines were extracted from
  `fonts/fontawesome-webfont.svg` at commit 0c26ed0.
- `.icon` in `css/style.css` (and in resume's inline style):
  `display:inline-block; height:1em; width:calc(W/1792 * 1em) per glyph or a per-icon
  width; vertical-align:-0.142857em; fill:currentColor; overflow:visible`. The vertical
  offset is the font's 256/1792 descent, which is where the glyph's baseline sat. Width per
  glyph: set `width` from the viewBox ratio with one `.icon-NAME` rule each, or set
  `width:auto` and rely on the viewBox aspect ratio with `height:1em` (verify in the
  screenshot diff which one matches; `width:auto` on an inline SVG with a viewBox resolves
  from the aspect ratio in current engines). Existing rules that size or color the glyph by
  selector (`.service-icon .fa`, `.contact-item .c-icon .fa`, `.single-service:hover
  .service-icon .fa`, and the `.fa` uses inside `.social-list`, `.footer-social-list`,
  `.scroll-up`, `.portfolio-stars`, `.portfolio-link`) are retargeted to `.icon`, keeping
  their `font-size` and `color`. Grep `css/style.css` for every `.fa` selector and carry each.
- Remove the `font-awesome.min.css` links from both pages.
- Do not delete files yet (task 5).

Commit: `feat: replace Font Awesome 4.7 with inline SVG icons` (with the test changes in a
preceding `test:` commit if the red run is committed separately).

As built (departures measured against the task 0 baseline, not reasoned):
- `width:auto` does not work: an inline `<svg>` with no width attribute is 300px wide
  whatever its height. Every icon gets a `.icon-NAME { width: W/1792 em }` rule, followed by
  `width: round(<same>, 1px)`, because the browser laid each glyph out at a whole-pixel
  advance; without the rounding the text after an icon moved by a fraction of a pixel.
  Symbols carry `preserveAspectRatio="xMinYMid meet"` so the rounding slack falls on the
  right, where a glyph leaves it.
- `.icon` has `margin-right: 1px`: the body's 1px letter-spacing was added after each glyph
  and does not apply to a replaced element. The about list's 4px icon margin becomes 5px.
- `.service-icon` and `.c-icon` set `line-height` 70px and 58px on the glyph. A replaced
  element has no line-height, so the half-leading becomes margin, (70 - 44) / 2 = 13px and
  (58 - 20) / 2 = 19px, carried into `vertical-align` too.
- `.footer-social-list li a` is inline-flex and takes its baseline from its first item; an
  `<svg>` has none, which lifted each icon link 2.4px. `a:has(> .icon)` gets
  `vertical-align: -0.142857em` to put it back.
- `resume.html` sizes its SVGs with a new `.glyph` class, not `.icon`: there `.icon` already
  means "blue, 8px right margin", and the Download PDF glyph never had it.

### Task 2: Vanilla main.js and a hand-written toggle

Red first, `verify_interactivity.py`:
- `check_script_tag`: main.js still loads; now fails if any page loads a script whose src
  contains `jquery` or `bootstrap`, instead of requiring jQuery before main.js.
- `check_no_dead_code`: add banned tokens `jQuery`, `$(` , `$.`, `.collapse(`, `.animate(`,
  `.fadeOut(`, each with a reason (no library provides them).
- New `check_nav_toggle`: the toggle is a `<button type="button">` with `aria-expanded`
  (`"false"` in the markup) and `aria-controls` naming an id that exists and wraps the nav
  list; it carries no `data-toggle`/`data-target`; it has an accessible name.
- New `check_native_smooth_scroll`: `css/style.css` sets `scroll-behavior: smooth` on `html`
  only inside `@media (prefers-reduced-motion: no-preference)`, and gives
  `.one-page-section` a `scroll-margin-top`. `main.js` contains no `scrollTo(`/`scrollTop =`
  driven animation for anchors (it must not fight the native scroll).
- `check_progress_bars` and `check_card_handler` unchanged.
- Update the module docstring.

Then `js/main.js`, vanilla, ES2015+ allowed (const, let, arrow functions; no modules, no
build). Keep the header comment's rule (every block has a matching element) and the block
structure. Required behaviors:
- Runs on `DOMContentLoaded` (or immediately if `document.readyState !== "loading"`).
- Loader: on `window` `load` (or immediately if `document.readyState === "complete"`), fade
  `.loader-con` opacity 1 to 0 over 600ms (jQuery's `"slow"`), then `display:none`. Port
  as-is, including that it fades regardless of reduced motion. Do it with an inline
  `transition` plus a `transitionend` listener and a 700ms timeout fallback, so a missed
  `transitionend` can never leave the page covered.
- `navHeight()`: header `offsetHeight` minus the open collapse's `offsetHeight` when the
  toggle reports `aria-expanded="true"`. Kept, because the active-link probe still needs it.
- `stickyNav()`: `.nav-sticky` at `scrollY >= 100`, `.show-up-btn` at `>= 1000`.
- Smooth scroll is native: no click handler on `a.scroll` and no handler on `.scroll-up`.
  The `href="#"` on `.scroll-up` scrolls to the top natively. CSS:
  `@media (prefers-reduced-motion: no-preference) { html.smooth-scroll { scroll-behavior: smooth; } }`
  (the class added after load; see As built) and
  `.one-page-section { scroll-margin-top: 63px; }` where 63px is the collapsed sticky header
  height measured in task 0 at both widths (6px padding top and bottom plus the 50px navbar
  plus the 1px border). If task 0 measures a different value at either width, use a media
  query per width; record the measurement in a comment.
- Mobile toggle: click flips `aria-expanded`, toggles `.is-open` on `#bm-navbar`. Clicking
  any link inside `#bm-navbar` closes it (sets `aria-expanded="false"`, removes `.is-open`).
  Closing happens in the click handler, which runs before the browser performs the fragment
  navigation, so the header is already collapsed when the browser resolves
  `scroll-margin-top`. That is what replaces the old `navHeight()` subtraction for scrolling.
- `changeActiveNavLink()`: same probe (`scrollY + navHeight()`), same "remove all, add one"
  rule. Section top from `getBoundingClientRect().top + scrollY`. Section extent: use
  `offsetHeight` (border box). jQuery's `.height()` returned the content box, so padding at
  the bottom of each section was a dead zone where the previous link stayed lit; using the
  border box closes that gap. This is a deliberate deviation, listed in the PR.
- `progressBars()`: same trigger (`sectionTop - (innerHeight - 160)`), same `.done` latch, sets
  `style.width = percent + "%"` from `data-percent`.
- One passive `scroll` listener throttled with `requestAnimationFrame`, plus one call on
  ready. Also a `resize` listener on the same throttle, since the old code had none and
  sticky/active state after a rotate depended on the next scroll (harmless addition; skip if
  it changes any task 0 metric).

CSS for the collapse (in task 3's nav block, but needed here): below 768px
`#bm-navbar` is hidden unless `.is-open` (`display:none` / `display:block`, matching
Bootstrap's `.collapse`/`.collapse.in`, so closed links are out of the tab order). Bootstrap
3 animated the open with a 350ms height transition; reproduce it with
`grid-template-rows: 0fr` to `1fr` on a wrapper plus `visibility` delayed by 350ms on close,
or with a JS-set `height` transition. Whichever is used, the closed menu must not be
focusable, and under `prefers-reduced-motion: reduce` it opens without the transition. At
768px and up the toggle is `display:none` and `#bm-navbar` is always shown, regardless of
`.is-open`.

Remove the `jquery.min.js` and `bootstrap.min.js` `<script>` tags. Commit:
`feat: rewrite main.js without jQuery and drop Bootstrap JS`.

As built:
- The collapse animation is the JS-set height transition, as Bootstrap ran it: `.is-open`
  shows the menu, `.is-collapsing` exists only for the 350ms, a `transitionend` filtered to
  the menu's own `height` (the links' color transitions bubble up too) plus a 400ms timeout
  ends it, and it is skipped when the toggle is hidden or reduced motion is set.
- `changeActiveNavLink()` probes at `scrollY + navHeight() + 1`. Section tops are fractional
  and scroll offsets whole, so a nav link landed its section up to 0.2px short and left the
  previous link lit; the drive's new "active link after landing" line caught it on the
  baseline as well (#services, #portfolio, #contact from mid page).
- `navHeight()` subtracts the open menu only while the toggle is shown, so a menu left open
  across a resize to 1440 does not shrink the probe there.
- Defect found by the task 5 edge path, fixed under a frozen test
  (`verify_interactivity.check_deep_link_is_not_animated`, commit 11085d1): with
  `scroll-behavior: smooth` on bare `html` from the first paint, Chrome animates the initial
  jump to `/#contact` toward an end point fixed before the portfolio cards and Lato arrive,
  and the section ended 11px (375) and 37px (1440) from the top, under the header. The rule
  is `html.smooth-scroll` instead, and `main.js` adds the class a frame after `load`.

### Task 3: Replace bootstrap.min.css

Red first:
- `verify_security.py`: replace `check_jquery_version` with
  `check_no_end_of_life_library`: for every page, every `<script src>` is a first-party path
  under `js/` and every `rel=stylesheet` href is under `css/` or is
  `https://fonts.googleapis.com/`; no src or href names `jquery`, `bootstrap`,
  `font-awesome`, or `fontawesome`. (The "those four files are absent from the tree" half
  moved to task 4, which is where they are deleted; asserted here it would hold task 3's
  commit red. `verify_assets.DEAD_ASSETS` carries it.) Drop the
  `JQUERY` constant and the CLAUDE.md version cross-check (there is no version left to name;
  the allowlist is what keeps a library from coming back unnoticed). Rewrite the comment in
  `check_no_unescaped_interpolation` that says jQuery is loaded on index.html: the point it
  makes (`.html()`/`.append()` bypass the check) becomes moot, so say no DOM library is
  loaded and the sinks listed are the native ones.
- `verify_seo_a11y.py`, a new `check_no_bootstrap_classes` (or inside an existing page
  sweep): no page and no class string in the renderer uses `col-(xs|sm|md|lg)-`,
  `col-*-offset-`, ` row` as a class token, `text-muted`, `navbar-right`, `collapse`,
  `data-toggle`, or `data-target`. And every class token on `index.html` that the old
  Bootstrap stylesheet styled and the markup still uses (`container`, `sr-only`,
  `text-center`, `navbar-header`, `navbar-collapse`, `navbar-nav`, `navbar-toggle`,
  `navbar-brand`, `icon-bar`, `nav`) has a rule in `css/style.css`; an unstyled `sr-only`
  label would silently render visible and blow the form height.
- Focus: replace the `a:focus:not(:focus-visible)` assertion. That rule existed only to beat
  `bootstrap.min.css`'s `a:focus { outline: 5px auto }`; the browser's own stylesheet keys
  its ring on `:focus-visible`, so with Bootstrap gone a mouse click paints no ring without
  any rule. The replacement asserts the condition the old rule protected: no stylesheet a
  page links (only `css/style.css` now) sets `outline` to anything but `none` in a rule whose
  selector contains `:focus` without `:focus-visible`, with `.skip-link:focus` exempt (it is
  documented as deliberately `:focus`). Then delete the rule and its comment from
  `css/style.css`. The live drive confirms it: mouse-click a nav link, computed `outline-style`
  is `none`; Tab to it, the 2px ring is present.
- `verify_content.py`, `check_contact_form_spacing_is_declared`: rewrite for whatever layout
  the form uses (below). The criterion it protects is the gaps, so it keeps asserting the
  rules that carry them; it drops `.submit-btn`'s `clear` only if the form no longer uses
  floats, and then asserts the form's grid declaration instead. Its docstring is updated to
  the new model.

Then the CSS. Method, so nothing Bootstrap supplied is lost silently:
1. Inventory: with Playwright on the baseline, at 375 (menu closed and open) and 1440, use
   Chrome's CSS coverage (`page.coverage` is JS-only in Python; use a CDP session:
   `CSS.startRuleUsageTracking` / `CSS.stopRuleUsageTracking`) to list every rule in
   `bootstrap.min.css` that matched something, and the properties it set that survive the
   cascade (`getComputedStyle` diff with and without the stylesheet is the fallback). Save
   the list to scratch.
2. Write local rules for what survives, by intent rather than copy: `box-sizing:border-box`
   on `*, *::before, *::after`; `html{font-size:10px; -webkit-tap-highlight-color:transparent}`;
   body font family, 14px/1.42857 size and line height, `#333` color, `#fff` background
   unless `style.css` already sets them; heading and `p`, `ul`, `label`, `button`/`input`/
   `textarea` font inheritance and margins that are not already overridden; `img`
   `vertical-align:middle`; `.container` (padding 15px, centered, `max-width` 750/970/1170 at
   768/992/1200, or the equivalent widths Bootstrap produced including its `width` values);
   `.sr-only` (the standard clip pattern Bootstrap 3 uses); `.text-center`; the navbar block
   (`.navbar-header` float, `.navbar-toggle` 44x34 with 8px vertical margins and the three
   22x2 `.icon-bar`s spaced 4px, `.navbar-brand` padding 15px and height 50px, `.nav` list
   reset, `.navbar-nav > li > a` padding 15px and line-height 20px at 768 and up, 10px
   vertical below, `.navbar-right` float right at 768 and up, `.navbar-collapse` padding and
   border-top below 768). Rename layout classes in the markup to site classes where the
   Bootstrap name no longer applies: about (`.about-grid`, two columns at 992+), the contact
   detail list inside about (two columns at 768+), services (`.services-grid`, three columns
   at 992+; the existing `.clear-float` and `.services-separator` keep working or are folded
   into the grid, whichever the screenshots match), portfolio (`#github-projects` already
   flex; its items keep `.portfolio-item` and drop `col-sm-6 col-md-4`; check what the
   existing `@media` rules for `.portfolio-item` do at each width and keep them), contact
   items (three columns at 768+ inside a 10/12 centered column at 992+), the form (two
   half-width fields at 768+, full-width textarea; CSS grid with `column-gap: 30px`), footer.
   Gutters: Bootstrap columns carry 15px side padding inside a `-15px` row; reproduce the
   resulting content positions, not the mechanism.
3. Remove the `bootstrap.min.css` link.
4. Pixel-diff against the baseline at both widths (C2a) and compare the C2b metrics. Iterate
   until every remaining diff is explained. The form height at 1440 must stay 387.5px, and
   its field positions must match.

Commit: `feat: replace the Bootstrap 3 stylesheet with local layout rules`.

As built:
- The inventory was the fallback the plan names: a `getComputedStyle` diff of every element
  and its `::before`/`::after`, with and without `bootstrap.min.css`, at 375 (closed, open)
  and 1440.
- One grid pattern for every former `.row`: the row's -15px margins on the grid, the
  column's 15px padding on each item, `align-items: start` (a stretched item would grow the
  skills panel's background). `.contact-col` is `display: flow-root`, because the float it
  replaced contained `#contact-form`'s 50px top margin. The 3-column tracks are
  `33.33333333%`, Bootstrap's own percentage, not `1fr`: it resolves 1/64px narrower, and the
  text in the second and third contact columns rasterized differently at the exact third.
- The form grid is `padding: 0 15px; column-gap: 30px`, fields in `.form-field` (positioned,
  for the sr-only labels), the textarea and button spanning both columns. `.submit-btn`
  loses `clear: both`; the textarea keeps its 68px.
- The footer's `.row` became `.footer-row` with the same -15px margins: dropping them
  narrowed the copyright paragraph by 30px, which at 375 changes where it can wrap.
- `.clear-float` (an empty element in a grid) is deleted with its rule; the separator spans
  the grid on its own.
- Deliberate visible changes, both from Bootstrap rules not carried over: the mobile toggle
  now shows the site's 2px keyboard focus ring (Bootstrap's `.navbar-toggle:focus { outline:
  0 }` hid every ring on it), colored white over the hero and dark on the sticky bar like the
  links; and the renderer's empty-state text is `#5a6268`, the loading text's color, where
  `.text-muted` was `#777`, 4.3:1 on the section's `#f8f9fa`.
- Not carried over: Bootstrap's `@media print` block, which only `index.html` loaded.
  `resume.html`, the page that gets printed, never loaded Bootstrap and keeps its own.

### Task 4: Delete the files and update the asset lists

Red first, `verify_assets.py`: move `js/jquery.min.js`, `js/bootstrap.min.js`,
`css/bootstrap.min.css`, `css/font-awesome.min.css`, and every `fonts/` file into
`DEAD_ASSETS` (so their return fails), remove them from `HOMEPAGE_ASSETS`, and drop
`fonts/fontawesome-webfont.woff2` from it. The red run fails on "is gone".

Then `git rm` the files. Every verifier must pass. Grep the whole tree (excluding
`docs/superpowers/plans/` and `.git`) for `jquery`, `bootstrap`, `font-awesome`,
`fontawesome`, `glyphicon`, `fa-`, `$(`, and confirm each remaining hit is prose that is
still true or a removed-asset list entry.

Commit: `chore: delete jQuery, Bootstrap, Font Awesome, and their fonts`.

### Task 5: Gate, live drive, measurements

1. The gate, verbatim, in the CI order: `python3 tools/verify_assets.py`,
   `python3 tools/verify_security.py`, `python3 tools/verify_content.py`,
   `python3 tools/verify_interactivity.py`, `python3 tools/verify_seo_a11y.py`,
   `python3 tools/verify_portfolio.py`. All exit 0, output captured.
2. The task 0 drive script against the branch: C2a diffs, C2b metric table before and after,
   C2c PASS lines at 375 and 1440, plus the reduced-motion pass and the focus-ring check
   (mouse click no ring, Tab ring present). Edge paths for High: activate a nav link with the
   375 menu open; reload with `#contact` in the URL (lands below the header, nav sticky,
   CONTACT active); resize 375 to 1440 with the menu open (menu shows inline, toggle hidden,
   nothing overlaps); JavaScript disabled (page renders, same as today: loader covers it,
   which is issue #32, not this one; record it, do not fix it).
3. Lighthouse 12 on `index.html` (accessibility, SEO) and `resume.html` accessibility in
   light and dark. Compare to the baseline.
4. C4 byte count before and after.
5. Which issue #33 criteria the native fragment navigation now happens to meet, each checked
   in the drive: next Tab after activating a nav link with Enter lands in or after the target
   section and the page does not scroll back; `location.hash` updates and Back returns to the
   previous section; heading lands below the header at both widths including with the menu
   open; reduced motion jumps. Report only; #33 is not worked here.

## Risks

- Highest: the Bootstrap base stylesheet. It sets dozens of properties the site never
  overrode (box-sizing, root font size, line height, heading margins, form control fonts,
  label weight, img alignment, list margins). Dropping it moves things by a few pixels
  everywhere. Mitigation: the coverage inventory plus the pixel diff against a baseline taken
  before any change; nothing ships with an unexplained diff.
- The contact form height (387.5px) depends on margin behavior inside floated columns that
  CLAUDE.md documents in detail. Moving the form to grid changes margin collapsing, so the
  textarea's 68px margin may need to change to keep the visible gap; measure, do not reason.
- Native smooth scroll changes three things compared to jQuery: the per-link `data-speed`
  durations go away (the browser picks the duration), the URL hash now updates on every nav
  click, and the landing offset becomes the same everywhere. Today, clicking a nav link from
  the top of the page at 1440 subtracts the 90px non-sticky header, then the header shrinks
  to 63px on arrival and leaves a 27px gap; clicking from mid-page lands flush. After the
  change both land flush. That is a deviation in the direction of the intended behavior, and
  it goes in the PR. Hash updates are what issue #33 asks for; the plan reports them against
  #33 rather than claiming #33.
- `scroll-margin-top` is a fixed value. If the sticky header height ever changes, the offset
  goes stale. The CSS comment names the measurement and the verifier asserts the property
  exists; the value itself is checked only by the live drive.
- The active-link extent changes from content box to border box (see task 2). If the
  orchestrator wants strict parity, swap `offsetHeight` for the content height; one line.
- The collapse animation: Bootstrap's 350ms height transition is approximated, not reused.
  The closed menu must stay out of the tab order (`display:none` or `visibility:hidden`).
- Icons: `<use>` against a `display:none` sprite works in every engine this site targets, but
  `display:none` on the sprite `<svg>` itself is required to not reserve space, and the
  symbols must sit in the same document as the `<use>` (no external sprite file, so no extra
  request and no CORS question). A typo in an icon name renders an empty box silently; the
  verifier's symbol-resolution check is what catches it.
- SVG `fill: currentColor` must reproduce the hover color changes on `.service-icon` and the
  social lists, which used `color` on the glyph. Driven in the screenshot pass at hover where
  practical; at minimum the computed `fill` equals the old computed `color` for each icon.
- Riskiest step to get wrong silently: weakening a verifier while "updating" it. Every
  removed check has a replacement named in this plan; the verifier subagent in Phase 7
  compares old and new check lists.

Chose not to do: Bootstrap 5 CSS (owner decided no framework); Font Awesome 6/7 self-hosted
(owner decided inline SVG); a JS smooth-scroll polyfill to keep `data-speed` (native is what
the issue recommends and it honors reduced motion in CSS); fixing the loader without JS
(#32) or adding focus management (#33); removing the dead carousel and popup CSS.

## Proof

| Criterion | Proof |
|---|---|
| C1a | `verify_security.check_no_end_of_life_library`, `verify_assets` DEAD_ASSETS, `verify_interactivity.check_script_tag`; the task 4 grep |
| C1b | `verify_seo_a11y.check_no_bootstrap_classes`, `verify_security.check_icons_are_inline_svg` |
| C1c | `verify_seo_a11y.AccessibleNames` (svg rule) and the renderer check; Lighthouse accessibility |
| C2a, C2b | `drive.py` screenshot diff and metric table, baseline vs branch, both widths |
| C2c | `drive.py` behavior pass PASS lines at 375 and 1440, reduced-motion pass, edge paths |
| C3 | the six verifier outputs; Phase 7 verifier compares old and new check lists |
| C4 | byte count before and after, in the PR |
| C5 | Lighthouse 12 JSON summaries for `index.html` and `resume.html` (light and dark) |

The live drive must show, at each width: the toggle state machine with `aria-expanded`
values; landing offset per nav link equal to the sticky header's bottom edge; sticky on and
off around 100px; back-to-top visible past 1000px and returning to 0; the active link at
each section in both scroll directions; skill bars 5% before and `data-percent` after; the
loader gone after load; the reduced-motion jump; no console errors.
