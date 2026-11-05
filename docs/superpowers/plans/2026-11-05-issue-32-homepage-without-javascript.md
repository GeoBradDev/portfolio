# Plan: Homepage is permanently blank without JavaScript (issue #32)

Risk tier: Medium. The rubric reads High (Low, raised once because the defect is a
load-time visual state no source check can fully exercise, and once because it alters
existing behavior; five files also change). Overridden to Medium by the orchestrator, on
the owner's behalf, when approving this plan: the change is a pure deletion of markup, CSS
and script with no security, data, or outward-message path, and the browser drive below
covers the load-time state the verifier cannot. Phase 5 runs one Claude finder plus one
Claude finder in the external reviewer's slot (no external review is configured).

Domain skills:
- superpowers:test-driven-development: invoke (implementer). The verifier check lands red
  before the deletion.
- superpowers:verification-before-completion: invoke (every phase that claims a result).
- frontend-design:frontend-design: not applicable because nothing new is designed; an
  element is removed.
- chrome-devtools-mcp:debug-optimize-lcp: not applicable because the change does not tune
  LCP; the probe below records first paint and LCP before and after as evidence only.
- chrome-devtools-mcp:a11y-debugging: not applicable because the chrome-devtools MCP server
  is not connected in this session; Lighthouse and Playwright cover the same ground.
- django, django-ninja-api, python-fastapi, expo:*, vercel-*: not applicable because this
  is a static HTML site with no framework.

## Defect, reconfirmed on f8eda33

The issue was filed against the jQuery site; line numbers below are current.

- Markup: `index.html` lines 120 to 127, `<div class="loader-con">` holding
  `<div class="spinner center">` with `.double-bounce1` and `.double-bounce2`.
- CSS: `css/style.css` "Pre Loader" section (about lines 463 to 503): `.loader-con` is
  `position: fixed`, `top: 0; left: 0; width: 100%; height: 100%`,
  `background-color: #fdfdfd`, `z-index: 99`; `.loader-con .spinner`; `.double-bounce1,
  .double-bounce2`; `.double-bounce2`. The keyframes `sk-bounce` (webkit, moz, unprefixed)
  under "PreLoader Animations" (about lines 1898 to 1932). Table of contents entry
  "2. Pre Loader" (line 13). The `.skip-link` comment (about line 285) names
  `.loader-con at 99` as something the skip link must beat.
- Script, the only two places that hide it:
  - `js/main.js` "Preloader" block: `hideLoader()` (fade over 600ms plus a 700ms timeout
    fallback), called from `onLoad()` on `window` `load`. `onLoad()` also adds the
    `html.smooth-scroll` class a frame later; that part stays.
  - `index.html` inline portfolio renderer, the `finally` of `loadPortfolio()`:
    `const loader = document.querySelector('.loader-con'); if (loader) loader.style.display = 'none';`
- No `<noscript>` anywhere in the repo. No verifier references the loader (the one
  `loader` hit in `tools/verify_security.py` is about the module loader, unrelated).
- `CLAUDE.md` line 97 says main.js "drives the loader fade"; line 308 says the skip link's
  `z-index: 200` clears `.loader-con` at 99.

Browser evidence (Playwright Chromium, `python3 -m http.server`, probe
`scratchpad/issue32/probe32.py`, output `scratchpad/issue32/before.json`, screenshots
`before-nojs-{375,1440}.png`):

- JavaScript disabled, 375x812 and 1440x900: `.loader-con` computed `display: block`;
  `elementFromPoint` at the hero `h1`, about `h2` and `p`, services `h2` and `h3`, contact
  `h2`, and the submit button returns `DIV.loader-con` every time. The screenshot is a
  blank `#fdfdfd` page with a grey dot.
- JavaScript enabled, throttled (150ms latency, 1.6 Mbps down, cache disabled), 3 runs per
  width: DCL about 1156ms, FCP about 1168ms, hero `h1` first uncovered about 1348ms, load
  2175ms at 375 and 3185ms at 1440. Today the hero is uncovered before `load` only because
  the renderer's `finally` hides the loader as soon as `projects.json` resolves; when that
  fetch is slow the overlay holds until whichever of the fetch or `load` comes first, and
  there is always a gap of about 180ms after first paint where parsed content sits under
  the overlay.

## Acceptance criteria

From the issue, verbatim, plus the checks this run adds:

1. With JavaScript disabled, `index.html` shows the hero, about, services, and contact
   content. The portfolio section may show nothing or a static note.
2. With JavaScript enabled, no overlay hides already-parsed content until `window` `load`.
3. All six verifiers pass.

Made checkable:

- AC1: at 375x812 and 1440x900 with JavaScript disabled, `elementFromPoint` at the hero
  `h1`, about `h2` and first `p`, services `h2` and first `h3`, contact `h2`, and the submit
  button returns that element or a descendant; screenshots show the content. The portfolio
  container is empty (accepted by the criterion; no `<noscript>` note is added).
- AC2: no element matching `.loader-con` exists; with JavaScript on under the same
  throttling, the hero `h1` is uncovered at or within one frame of FCP (not about 180ms
  after), and with `projects.json` delayed by 3000ms via a Playwright route it is still
  uncovered at FCP (on f8eda33 it waits for the delayed fetch or `load`).
- AC3: all six verifiers exit 0, and the new check in `tools/verify_interactivity.py`
  fails on f8eda33 and on the mutations listed under Proof.
- AC4 (no regression): the portfolio section still shows "Loading portfolio projects..."
  then cards, and the error state still renders on a failed fetch; nav, active link,
  sticky nav, mobile toggle, skill bars, smooth scroll, and issue 33 focus handling behave
  as on f8eda33; a deep link to `/#contact` still lands with `#contact` at the header
  offset after the portfolio renders above it; Lighthouse accessibility and SEO stay 100
  on `index.html`.

## Files that change

- `tools/verify_interactivity.py`: new `check_no_script_removed_overlay(html, css, js)`,
  called from `main()`; module docstring gains an issue 32 paragraph.
- `index.html`: delete the loader markup and its `<!-- Loader -->` / `<!-- End Loader -->`
  comments; delete the renderer's `finally { ... }` block (the `try`/`catch` stays intact).
- `css/style.css`: delete the "Pre Loader" section (`.loader-con`, `.loader-con .spinner`,
  `.double-bounce1, .double-bounce2`, `.double-bounce2`), the three `sk-bounce` keyframe
  blocks and their "PreLoader Animations" comment, and the "2. Pre Loader" line of the
  table of contents (renumber the entries after it). Rewrite the `.skip-link` comment so
  it names only `.nav-wrapper` at 20. Leave `.skip-link`'s `z-index: 200` as is. Keep
  `.center` (the hero chevron's `.dot` uses it) and `@keyframes spin` (the portfolio
  loading spinner uses it).
- `js/main.js`: delete the "Preloader" banner comment and `hideLoader()`; `onLoad()` keeps
  only the `requestAnimationFrame` that adds `smooth-scroll`. Its comment loses nothing it
  needs; the file header comment needs no change (it does not mention the loader).
- `CLAUDE.md` (Phase 8): drop "the loader fade" from the js/main.js summary; drop
  `.loader-con at 99` from the skip-link bullet; add one bullet under Accessibility stating
  the rule (nothing covers the page by default and waits for script to uncover it; issue
  32 deleted the loader for that reason; `verify_interactivity.py` enforces it).

## Order of work

1. Commit this plan alone: `docs: plan for issue 32`.
2. Red: add `check_no_script_removed_overlay` to `tools/verify_interactivity.py` and call
   it from `main()`. Run `python3 tools/verify_interactivity.py` against the unchanged tree
   and save the FAIL output to `scratchpad/issue32/red.txt`. Commit:
   `test: forbid an overlay only script removes (issue 32)`. Freeze it (honor the freeze;
   there is no edit-guard hook in this repo).
   The check has two parts:
   - Narrow: with HTML comments stripped from `index.html`, no element carries the class
     token `loader-con`, `double-bounce1`, or `double-bounce2`; with CSS comments stripped
     from `css/style.css`, no selector names `.loader-con` or `.double-bounce` and no
     `@keyframes sk-bounce` survives; neither `js/main.js` (through `strip_js_comments`) nor
     the inline scripts of `index.html` contain the string `loader-con`.
   - General: for every rule `css_rules()` returns from comment-stripped `css/style.css`
     (so rules inside `@media` and `@supports` count), and for every `style` attribute in
     `index.html`, a declaration block that sets `position: fixed` and covers the viewport
     horizontally (`width: 100%` or `100vw`, or `left: 0` and `right: 0`, or `inset: 0`) and
     vertically (`height: 100%` or `100vh`, or `top: 0` and `bottom: 0`, or `inset: 0`) fails
     unless the same block hides it (`display: none`, `visibility: hidden`, or
     `opacity: 0`). The message says that with JavaScript off nothing removes it, and
     points at issue 32. `.nav-wrapper` (full width, no height) and `.scroll-up` (46px)
     must not trip it, and neither may the open mobile menu or any other existing rule at
     375 or 1440: the red run must name only the loader (`.loader-con` and its pieces).
3. Green: delete the markup, CSS, and script listed under Files that change. Run the full
   gate. Commit: `fix: delete the full-screen loader so the page renders without JavaScript (issue 32)`.
4. Mutation proof of the new check, on scratch copies, never committed: each of these
   must FAIL, then the tree must PASS again.
   - Re-add `.splash { position: fixed; inset: 0; background: #fff; }` to `css/style.css`.
   - Re-add `.splash { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; }`
     inside an `@media (min-width: 0)` block.
   - Re-add `<div style="position:fixed;top:0;right:0;bottom:0;left:0;background:#fff"></div>`
     to `index.html`.
   - Re-add `<div class="loader-con"></div>` to `index.html` with no CSS.
   - Re-add `document.querySelector('.loader-con')` to `js/main.js`.
   And these must PASS: the same `.splash` rule with `display: none` in its block; a
   comment in `css/style.css` that says `.loader-con` was removed.
5. Live drive (Playwright, scratch only): see Proof.
6. Phase 8 docs: `CLAUDE.md` edits above. Commit:
   `docs: record the issue 32 no-overlay rule in CLAUDE.md`.

## Risks

- Deep links. The overlay used to hide the moment the portfolio renders above
  `#contact` and grows the page. Without it, a visitor on `/#contact` sees the jump
  happen unless scroll anchoring holds the position. Chromium anchors by default; the
  drive checks the final `#contact` offset after render at both widths, with
  `projects.json` delayed so the render lands after the initial jump.
- Breaking `onLoad()`. `check_smooth_scroll_starts_on_load` (issue 31/33) requires the
  `smooth-scroll` class to be added from the window load path. Removing `hideLoader()` must
  leave `onLoad()` registered on `load` and still adding the class in a
  `requestAnimationFrame`. The gate catches a break.
- Collateral CSS deletion. `.center` and `@keyframes spin` look like loader CSS but are
  used by the hero chevron and the portfolio loading spinner. The plan keeps both; the
  drive screenshots the chevron and the loading state.
- Over-broad check. The general rule could flag a legitimate future full-screen element
  that script opens (a modal or menu) when its hidden state lives in another rule. That is
  intended: such an element must be hidden in its own base rule and shown by a class, and
  the failure message says so. Known limit: the check reads `css/style.css` and
  `index.html` inline styles only; an overlay created entirely by script, or one whose
  coverage comes from a combination of rules, is not caught.
- Font swap. Without the overlay the first paint may show the fallback font before Lato
  arrives. Accepted: content in a fallback font beats no content, which is the issue's
  point.

What this deliberately does not do: no `<noscript>` note in the portfolio section (the
criterion allows an empty section); no change to `.skip-link`'s `z-index`; no cleanup of
the other dead template CSS (`.home-carousel` and similar), which has no open issue and
is out of scope.

## Proof

- AC3 and the guard: `scratchpad/issue32/red.txt` (new check FAILs on the unchanged tree,
  naming the `.loader-con` markup, selector, keyframes, script references, and the
  fixed full-viewport rule); the mutation runs from Order of work step 4; all six
  verifiers PASS after the fix, output captured per verifier.
- AC1: `probe32.py` against the branch with JavaScript disabled at 375x812 and 1440x900:
  every target's `topHit` is true; viewport and full-page screenshots
  `after-nojs-{375,1440}.png` and `after-nojs-{375,1440}-full.png` show hero, about,
  services, and contact.
- AC2: `probe32.py` with JavaScript on, 3 throttled runs per width, compared with
  `before.json`: `heroUncovered` minus `fcp` drops from about 180ms to one frame or less.
  A second variant with `projects.json` delayed 3000ms: on f8eda33 `heroUncovered` waits
  for the fetch or `load`; on the branch it matches FCP. Same probe shows the portfolio
  loading text during the delay and cards after it.
- AC4: rerun the issue 31 drives (`impl/drive.py`, `impl/drive2.py`) and the issue 33
  drives (`issue33/drive33c.py`, `issue33/hist33.py`) against f8eda33 and the branch.
  Each waits on `.loader-con` reaching `display: none`, which throws once the element is
  gone, so copy them into `scratchpad/issue32/` and change only that wait to accept an
  absent element (`!el || getComputedStyle(el).display === 'none'`); record the one-line
  diff of each copy. Results must match f8eda33 apart from the loader itself. Add a deep
  link drive: `/#contact` at 375 and 1440 with `projects.json` delayed 1500ms, `#contact`
  top within 2px of the header offset after the cards render. Error state: route
  `projects.json` to a 500 and confirm `.portfolio-error` renders.
- Lighthouse: `npx --yes lighthouse@12 http://127.0.0.1:8000/ --only-categories=accessibility,seo --chrome-flags="--headless"`
  on the branch: accessibility 100, SEO 100.
