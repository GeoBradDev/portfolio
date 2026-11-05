# Plan: Nav links and hero chevron scroll without moving focus (issue #33)

Risk tier: Medium. Nothing forces High. It starts at Low and raises twice: the behavior is
keyboard and focus interaction that no source-level check can exercise, so the only real
proof is a browser at two widths; and it alters existing behavior (where focus sits after
every in-page link) rather than adding. The diff is small: one attribute on five elements,
one CSS rule, one verifier check, docs.

Domain skills:
- superpowers:test-driven-development: invoke. The verifier check is written and run red
  before the markup and CSS that turn it green, and the browser drive is run red against
  `origin/main` before the fix.
- superpowers:verification-before-completion: invoke before any success claim.
- chrome-devtools-mcp:a11y-debugging: not applicable because its MCP server failed to connect
  this session; the same focus and keyboard checks run in Playwright Chromium instead.
- frontend-design:frontend-design: not applicable because nothing visual changes. The one CSS
  rule removes a ring the change would otherwise introduce.
- Every other listed skill (Django, Expo, React, FastAPI, data viz): not applicable because
  this is a static HTML and vanilla JS site.

## Background: what issue #31 already delivered

The issue was filed against the jQuery `a.scroll` handler, which cancelled the click and
animated `scrollTop`. Issue #31 (PR #38) deleted that handler. Navigation is now native
fragment navigation: `html.smooth-scroll { scroll-behavior: smooth }` under
`prefers-reduced-motion: no-preference`, and `.one-page-section { scroll-margin-top: 63px }`.

Measured in Phase 1 with Playwright Chromium against `origin/main` (654f193), keyboard only,
at 375x812 (menu opened with the toggle first) and 1440x900, for all five nav links, the
chevron, and the skip link. Drive script and output:
`/tmp/claude-1000/-home-bradstricherz-WebstormProjects-portfolio/d1665385-8056-4e41-b7d4-da502d9b6e32/scratchpad/issue33/drive33.py`, `/tmp/claude-1000/-home-bradstricherz-WebstormProjects-portfolio/d1665385-8056-4e41-b7d4-da502d9b6e32/scratchpad/issue33/baseline.txt`.

- Hash updates on every link; Back from CONTACT returns to `#about` at the same `scrollY`.
- Every target section's top lands at the header bottom (63.0, within 0.5px) at both widths.
- Reduced motion jumps (same `scrollY` at 20ms and 620ms); no-preference animates.
- The next Tab already reaches the first focusable element in or after the target section and
  never scrolls back. Chromium moves the sequential focus navigation starting point on
  fragment navigation. SERVICES has no focusable content, so Tab goes on to Portfolio's
  first Code link, scrolling forward.
- **The remaining gap:** after Enter, `document.activeElement` is `<body>` for every link.
  Chromium blurs the link because the target section is not focusable. Focus never moves into
  the section, so nothing tells assistive technology the reading position moved, which is the
  issue's screen reader complaint. It also leaves criterion 1 resting on a Chromium starting
  point heuristic rather than on focus itself, which is weaker in other engines.

## Approach

Make every in-page link target programmatically focusable with `tabindex="-1"` and let the
browser do the rest. HTML's "scroll to the fragment" runs the focusing steps on the target;
once the target is focusable it receives real focus. No JavaScript is added.

Proven before planning by rewriting `index.html` in flight
(`/tmp/claude-1000/-home-bradstricherz-WebstormProjects-portfolio/d1665385-8056-4e41-b7d4-da502d9b6e32/scratchpad/issue33/probe_tabindex.py`): with `tabindex="-1"` on the sections,
`document.activeElement` is the target section after Enter, the smooth scroll still animates
across frames (not cut short by the focus), the section top still lands at 63px, and the next
Tab reaches the same element as before.

Why not the JavaScript route the issue sketched (focus on hashchange with `preventScroll`):
`hashchange` does not fire when the visitor activates the link for the section the hash
already names, so a second CONTACT after scrolling away would scroll but not move focus;
covering that means a click listener plus a deferred focus, which is the "script fighting the
native scroll" `verify_interactivity.py` exists to forbid. The attribute covers every link,
same-hash re-activation, and the skip link, for free.

The focus ring on the section. The probe shows Chromium matches `:focus-visible` on the
section after a keyboard Enter and paints its UA `outline: auto 1px` around the entire
section. Suppress it with `.one-page-section:focus { outline: none; }`. Reasoning:

- SC 2.4.7 Focus Visible covers keyboard operable UI components. A `tabindex="-1"` section is
  not operable and not in the tab order; it is a reading position, not a control.
- The ring carries no location information: the section has just been scrolled to the top of
  the viewport under the header, and it is several viewports tall, so the ring is mostly off
  screen.
- Every operable control keeps its `:focus-visible` ring. The next Tab lands on one.
- `verify_seo_a11y.py`'s plain-`:focus` sweep permits it: `outline: none` paints no ring.

Known side effect, accepted: a mouse click on non-interactive content inside a section now
focuses that section (the nearest focusable ancestor). With the ring suppressed this is
invisible, text selection is unaffected, and the next Tab continues from that section, which
is what the sequential focus starting point already did.

Back to top (`<a href="#" class="scroll-up">`) is left as is. `#` targets the top of the
document, not an element, so focus goes to `<body>` and the next Tab lands on the skip link,
the first focusable element on the page, at `scrollY` 0. That is the right result for a back
to top control; the drive asserts it.

## Acceptance criteria

From the issue, verbatim:

1. After activating any nav link or the chevron with Enter, the next Tab moves to the first
   focusable element in or after the target section, and the page does not scroll back.
2. Activating a nav link updates `location.hash`, and the browser Back button returns to the
   previous section.
3. The heading still lands below the fixed navbar at 375px and 1440px, including with the
   mobile menu open.
4. `prefers-reduced-motion: reduce` still jumps without animating.
5. All six verifiers pass.

Added in Phase 1, from the issue's screen reader paragraph and the orchestrator's brief:

6. After activating any nav link, the chevron, or the skip link, `document.activeElement` is
   the target section, and that section paints no focus outline.
7. Back to top lands at `scrollY` 0 and the next Tab does not scroll away from the top.
8. `tools/verify_interactivity.py` fails when any element an in-page link targets lacks
   `tabindex="-1"`, carries a non-negative `tabindex`, or when `css/style.css` stops
   suppressing the outline on a focused `.one-page-section`.
9. Lighthouse accessibility and SEO stay 100 on `index.html`.

## Files that change

- `tools/verify_interactivity.py`: new check, `check_link_targets_take_focus(facts, css)`,
  wired into `main()` after `check_nav_targets`. `IndexFacts` additionally records every
  in-page fragment link of any class (`fragment_targets`, so the skip link, which carries no
  `scroll` class, is covered) and the `tabindex` attribute per id (`tabindex`). The check:
  every fragment target exists and carries `tabindex="-1"` exactly (a missing attribute fails,
  as does `0` or any positive value, which would put a section into the tab order); and the
  comment-stripped CSS has a rule whose selector list contains `.one-page-section:focus` with
  `outline: none` (or `outline: 0`). Bare `#` is excluded, as `nav_targets` already does.
  Update the module docstring's paragraph listing what it checks.
- `index.html`: `tabindex="-1"` on the five `<section class="... one-page-section">` elements
  (`#home`, `#about`, `#services`, `#portfolio`, `#contact`). A short HTML comment above
  `#home`, or beside the nav comment that already discusses targets, saying why. The comment
  must not quote a bare `<a ...>` or `<img ...>` tag (the verifiers strip comments, but keep
  it plain).
- `css/style.css`: `.one-page-section:focus { outline: none; }` placed directly after the
  existing `.one-page-section { scroll-margin-top: 63px; }` rule, with a comment carrying the
  reasoning above in two or three sentences.
- `js/main.js`: header comment only. Its "Smooth scrolling is the browser's" paragraph gains
  one sentence: focus is the browser's too, because each section is `tabindex="-1"` and native
  fragment navigation focuses a focusable target. No code change.
- `CLAUDE.md`: Phase 8 reconciles. Likely the Accessibility section gains one invariant
  (sections are `tabindex="-1"` so fragment navigation moves focus; the outline is suppressed
  on them only; do not add a click handler for it), and the `js/main.js` "Navigation &
  Scrolling" bullets are checked against reality.

Nothing else. No `package.json`, no build step, no test runner in the repo. The browser drive
lives in the scratch directory, as the #31 drive did.

## Order of work

1. Red: add `check_link_targets_take_focus` to `verify_interactivity.py`. Run it on the
   unchanged tree; it must FAIL naming all five sections and the missing CSS rule. Commit
   `test: require in-page link targets to take focus (issue 33)`.
2. Red in the browser: run `/tmp/claude-1000/-home-bradstricherz-WebstormProjects-portfolio/d1665385-8056-4e41-b7d4-da502d9b6e32/scratchpad/issue33/drive33.py` against the unchanged tree served on
   a local port; the "focus moved into" lines FAIL (14 of them, as in Phase 1). Save output.
3. Green: add the `tabindex="-1"` attributes and the CSS rule. Rerun the check: PASS. Mutation
   test the check by hand (scratch copies, never committed): remove the attribute from one
   section; set it to `0`; delete the CSS rule; change the rule to `outline: 2px solid`. Each
   must FAIL. Commit `fix: move focus into the section a nav link targets (issue 33)`.
4. Comments: the `js/main.js` header sentence. Commit with step 3 or as `docs:`.
5. Gate: all six verifiers, in the order listed in CLAUDE.md.
6. Live drive: `drive33.py` extended with a check that the focused section's computed
   `outline-style` is `none`, a same-hash re-activation case (hash already `#contact`, scroll
   to top, Enter on CONTACT again: focus on `#contact`, lands at 63px), and a mouse click on a
   nav link at 1440 (focus on the section, no outline), a mouse drag across a paragraph inside
   `#about` (the selection is non-empty, which proves the accepted side effect leaves text
   selection working), and a mouse click into a contact form field (focus is the field, not
   `#contact`). Run at 375 (menu open) and 1440, no
   preference and reduced motion. Expect `FAILS 0`, `ERRORS none`.
7. Lighthouse accessibility and SEO on `index.html` served locally: both 100.

## Risks

- Riskiest step: the focus interrupting or retargeting the smooth scroll. The probe showed it
  does not in Chromium, but the drive must re-prove it at both widths with the menu open,
  since the menu closes during the same click.
- A section ring appearing anyway via a more specific rule (`.home-1 a:focus-visible` etc. only
  target anchors, so none is expected). The drive reads computed `outline-style`.
- `verify_seo_a11y.py`'s "first focusable element is the skip link" scan: its regex matches
  only `a[href]`, `button`, `input`, `select`, `textarea`, so a `tabindex="-1"` section does
  not displace the skip link. `tabindex="-1"` is also not in the tab order, so the runtime
  answer is the same.
- Lighthouse: `tabindex="-1"` on a non-interactive element raises no audit; only positive
  tabindex does (`tabindex` audit). Confirmed by running it.
- Not chosen: `aria-labelledby` on each section to make it a named region landmark. It would
  make screen readers announce the section name on focus, but it adds five landmarks and
  changes the page's landmark structure, which the issue does not ask for. Mentioned in the PR
  as a possible follow-up, not done.

## Proof

| Criterion | Proof |
| --- | --- |
| 1 | `drive33.py`: per link and width, the element focused after Tab equals the first focusable element in or after the target, and `scrollY` did not decrease |
| 2 | `drive33.py`: `location.hash` per link; ABOUT, CONTACT, Back returns to `#about` at the same `scrollY` |
| 3 | `drive33.py`: target top within 1px of header bottom at 375 (menu open) and 1440 |
| 4 | `drive33.py`: reduced motion `scrollY` equal at 20ms and 620ms; no-preference differs at 60ms |
| 5 | The six verifier outputs |
| 6 | `drive33.py`: `document.activeElement` is the target section; computed `outline-style` `none`; same-hash re-activation case |
| 7 | `drive33.py`: back to top `scrollY` 0 before and after Tab |
| 8 | `verify_interactivity.py` red run before the fix, plus the four hand mutations each failing |
| 9 | Lighthouse output |
