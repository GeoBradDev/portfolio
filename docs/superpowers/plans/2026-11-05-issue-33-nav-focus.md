# Plan: Nav links and hero chevron scroll without moving focus (issue #33)

Risk tier: Medium. Nothing forces High. It starts at Low and raises twice: the behavior is
keyboard and focus interaction that no source-level check can exercise, so the only real
proof is a browser at two widths; and it alters existing behavior (where focus sits after
every in-page link) rather than adding. The diff is small: one click listener in `js/main.js`,
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

Revised after review (see Approval). The first version put a static `tabindex="-1"` on
every section. It moved focus correctly on link activation, but review confirmed a
regression: with the sections permanently focusable, a mouse click or tap on any
non-control content inside a section focuses the section (its nearest focusable ancestor),
so the next Tab restarts at the section's first control instead of continuing after the
clicked point. Measured at 375x812: click a lower portfolio card's padding at `scrollY`
4937, then Tab. On `main` focus goes to the next link (the chromewebstore Live Demo) and
`scrollY` stays 4937; on the static-attribute commit (f7bc742) focus goes back to the first
card's Code link and `scrollY` drops to 4150. Probe:
`/tmp/claude-1000/-home-bradstricherz-WebstormProjects-portfolio/d1665385-8056-4e41-b7d4-da502d9b6e32/scratchpad/issue33/finder2/probe2.py`.

So the target is made focusable only for the activation. `js/main.js` gains one click
listener on `document`. For a primary-button click with no modifier key that was not
already cancelled, it finds `event.target.closest('a[href^="#"]')`, looks the fragment up
with `getElementById`, and returns if there is no such element (a bare `#` names none, so
back to top is untouched) or if the target already carries a `tabindex`. Otherwise it sets
`tabindex="-1"` and does not cancel the click. The browser's own fragment navigation then
runs the focusing steps on a now focusable target and focus moves into it. The attribute
is removed on the target's first `blur`, and on a `setTimeout` of 0, if focus did not land
on the target, the blur listener and the attribute are removed at once. Keyboard Enter on a
link fires `click`, so the keyboard path is covered; a modified click opens a new tab or
window and is left alone. Proven by injection before the rewrite
(`.../scratchpad/issue33/coord/inject.js`, `probe_dyn.py`).

Why not focus on `hashchange` with `preventScroll`, as the issue sketched: `hashchange` does
not fire when the visitor activates the link for the section the hash already names, so a
second CONTACT after scrolling away would scroll but not move focus. The click listener sees
every activation, including same-hash, and it neither scrolls nor cancels anything, so it
does not fight the native scroll `verify_interactivity.py` protects.

The focus ring on the section. Chromium matches `:focus-visible` on the section after a
keyboard Enter and paints its UA `outline: auto 1px` around the entire section. Suppress it
with `.one-page-section:focus { outline: none; }`. Reasoning:

- SC 2.4.7 Focus Visible covers keyboard operable UI components. The focused section is not
  operable and not in the tab order; it is a reading position, not a control.
- The ring carries no location information: the section has just been scrolled to the top of
  the viewport under the header, and it is several viewports tall, so the ring is mostly off
  screen.
- Every operable control keeps its `:focus-visible` ring. The next Tab lands on one.
- `verify_seo_a11y.py`'s plain-`:focus` sweep permits it: `outline: none` paints no ring.

Known limit, accepted and narrow: while a section still holds focus from a link (the
attribute stays until the section blurs), a mouse click on non-control content inside that
same section keeps focus on it, so the next Tab restarts from the section top rather than
after the clicked point. Any other click, any Tab, or any click outside the section clears
it, and every later click behaves as on `main`.

Back to top (`<a href="#" class="scroll-up">`) is left as is. `#` targets the top of the
document, not an element, so the handler returns early, focus goes to `<body>`, and the next
Tab lands on the skip link, the first focusable element on the page, at `scrollY` 0. That is
the right result for a back to top control; the drive asserts it.

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
8. `tools/verify_interactivity.py` fails when an in-page link targets anything but a
   `.one-page-section`; when any element carries a static `tabindex` of 0 or more, or a
   target section carries any static `tabindex`; when `js/main.js` lacks the document click
   listener that selects `a[href^="#"]`, sets `tabindex="-1"`, and removes it again; and
   when the last on-screen `.one-page-section:focus` rule stops leaving the outline hidden
   (including `outline-style` or `outline-width` undoing it, or a visible outline under a
   non-print `@media`).
10. After focus leaves a section a link moved it into, the section carries no `tabindex`;
    a modified (ctrl) click on a nav link adds none; and a mouse click on non-control
    content followed by Tab behaves exactly as on `main` (probe2.py, six rows).
9. Lighthouse accessibility and SEO stay 100 on `index.html`.

## Files that change

- `tools/verify_interactivity.py`: `check_link_targets_take_focus(facts, css, js)`, wired
  into `main()` after `check_nav_targets`. `IndexFacts` records every in-page fragment link
  of any class (`fragment_targets`, so the skip link, which carries no `scroll` class, is
  covered), the `tabindex` attribute per id, and every element with a `tabindex`. The check
  asserts criterion 8. It reads the handler from the comment-stripped `js/main.js`: a function
  passed to `document.addEventListener("click", ...)` (inline or named) whose body holds the
  `closest('a[href^="#"]')` selection and `setAttribute("tabindex", "-1")`, and whose body
  also holds `removeAttribute("tabindex")`. Bare `#` is excluded, as `nav_targets` already
  does. The existing banned-pattern check still rejects `preventDefault` and scripted scrolls
  anywhere in the file.
- `index.html`: no `tabindex` in the markup. The static attributes and their comment from
  f7bc742 are removed.
- `css/style.css`: `.one-page-section:focus { outline: none; }` directly after the existing
  `.one-page-section { scroll-margin-top: 63px; }` rule, its comment saying a section is
  focusable only while a link has just moved focus there.
- `js/main.js`: the click listener, inside `init()`, under its own section banner, in the
  file's ES5 style. The header's "Smooth scrolling is the browser's" paragraph says focus is
  moved by the browser too, with the listener only making the target focusable for that one
  activation.
- `CLAUDE.md`: Phase 8 reconciles. Likely the Accessibility section gains one invariant
  (sections carry no static `tabindex`; the click listener adds and removes it; the outline
  is suppressed on them only), and the `js/main.js` "Navigation & Scrolling" bullets are
  checked against reality.

Nothing else. No `package.json`, no build step, no test runner in the repo. The browser drive
lives in the scratch directory, as the #31 drive did.

## Order of work

1. Red (done, 293d39a, then rewritten): the first check required the static attribute. After
   review it was rewritten (see Approval) and committed alone as
   `test: require focus to move only on link activation (issue 33)`. It must be red on
   `origin/main` (654f193) and on f7bc742; both outputs are under Proof.
2. Red in the browser: `drive33b.py` against f7bc742's parent showed the focus lines failing;
   probe2.py against f7bc742 shows the Tab order regression.
3. Green: remove the static attributes, add the click listener, update the comments. Rerun the
   check: PASS. Commit `fix: move focus only when a link is activated (issue 33)`. Mutation
   test on scratch copies, never committed, each must FAIL: handler missing; handler calls
   `event.preventDefault()`; handler never removes the attribute; a static `tabindex="-1"`
   back on one section; `tabindex="0"` on a section; outline rule deleted; outline rule only
   inside `@media print`; a later `.one-page-section:focus { outline: 2px solid }`;
   `outline-style: solid` inside the rule; a fragment link to a non-section id.
4. Gate: all six verifiers, in the order listed in CLAUDE.md.
5. Live drive: `drive33b.py` at 375 (menu open) and 1440, no preference and reduced motion:
   focus moves into the target, computed `outline-style` `none`, same-hash re-activation,
   mouse click on a nav link at 1440, drag-select in `#about`, click into `#name` and
   `#message`; plus: after Tab away from a focused section it has no `tabindex`, and after a
   ctrl-click on a nav link at 1440 the target has no `tabindex`. `probe2.py` against the
   branch and against `main`, six rows matching. `frames33.py`: the smooth scroll still
   animates frame by frame. Expect `FAILS 0`, `ERRORS none`.
6. Lighthouse accessibility and SEO on `index.html` served locally: both 100.

## Risks

- Riskiest step: the focus interrupting or retargeting the smooth scroll. The probe showed it
  does not in Chromium, but the drive must re-prove it at both widths with the menu open,
  since the menu closes during the same click.
- A section ring appearing anyway via a more specific rule (`.home-1 a:focus-visible` etc. only
  target anchors, so none is expected). The drive reads computed `outline-style`.
- `verify_seo_a11y.py`'s "first focusable element is the skip link" scan: the markup carries
  no `tabindex` now, and a section the listener makes focusable for a moment is not in the
  tab order, so the skip link stays first.
- The listener must not cancel the click or scroll. It calls neither; the existing
  banned-pattern check fails the gate if it ever does.
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
| 8 | `verify_interactivity.py` red on `origin/main` and on f7bc742 (below), plus the ten hand mutations each failing |
| 9 | Lighthouse output |
| 10 | `drive33b.py` tabindex-removed and ctrl-click lines; `probe2.py` rows on the branch equal to `main` |

### Red runs of the rewritten check

On `origin/main` (654f193), archive copy with only the rewritten verifier dropped in:

```
FAIL: 2 check(s) failed

  - js/main.js has no click listener on document that selects the activated fragment link with closest('a[href^="#"]') and sets tabindex="-1" on its target, so a nav link scrolls but leaves focus on <body>.
  - css/style.css does not leave the outline hidden on a focused .one-page-section (the last on-screen `.one-page-section:focus` rule must set outline: none), so a nav link paints a focus ring around the whole section it lands on.
```

On f7bc742's tree (the static attribute approach) with the rewritten verifier:

```
FAIL: 6 check(s) failed

  - #about carries a static tabindex="-1". A mouse click or tap inside the section then focuses it, and the next Tab restarts at its first control; js/main.js adds the attribute only when a link is activated.
  - #home carries a static tabindex="-1". A mouse click or tap inside the section then focuses it, and the next Tab restarts at its first control; js/main.js adds the attribute only when a link is activated.
  - #services carries a static tabindex="-1". A mouse click or tap inside the section then focuses it, and the next Tab restarts at its first control; js/main.js adds the attribute only when a link is activated.
  - #portfolio carries a static tabindex="-1". A mouse click or tap inside the section then focuses it, and the next Tab restarts at its first control; js/main.js adds the attribute only when a link is activated.
  - #contact carries a static tabindex="-1". A mouse click or tap inside the section then focuses it, and the next Tab restarts at its first control; js/main.js adds the attribute only when a link is activated.
  - js/main.js has no click listener on document that selects the activated fragment link with closest('a[href^="#"]') and sets tabindex="-1" on its target, so a nav link scrolls but leaves focus on <body>.
```

## Approval

Frozen test rewritten with approval from the orchestrator, on the owner's behalf, 2026-11-05.
Rationale: the test was written on this unmerged branch for an approach the evidence showed
to regress mouse and touch Tab order; the replacement asserts the corrected behavior and is
stronger (it adds the three hardenings), so this is a correction, not a weakened gate.
