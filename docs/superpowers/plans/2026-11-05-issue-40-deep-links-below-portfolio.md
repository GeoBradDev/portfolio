# Plan: Deep links below the portfolio land in the wrong place once the cards render (issue #40)

Risk tier: Medium. A layout and scroll behavior change that no unit test can exercise (only a
browser shows where a deep link lands), and it alters existing card CSS rather than adding beside
it. Raised from Low twice; not High, because it touches no security, data, or outward path.

Approval: approved at Medium tier on 2026-11-05 by the orchestrator on the owner's behalf, with
three answers: both mechanisms (reservation plus `overflow-anchor`); the card count lives in
`css/style.css` by hand, the gate fails on drift, and `tools/build_projects.py` also warns at
generation time without editing the stylesheet; the Safari-only error and empty residual is
accepted and stated in the PR body.

Frozen-test rewrite: approved on 2026-11-05 by the orchestrator on the owner's behalf. The fake
fetcher in `check_generator_main_warns` returned the repo for every entry in `ACCOUNTS`, so the
real `main()` wrote 2 cards and both of its assertions, which expect 1, failed against correct
production code. A fixture bug in the test's own setup. Only the fetcher changed, to return the
repo for the first account alone; no assertion changed.

Round 1 review: directed by the orchestrator on 2026-11-05. The check is revised in its own red
commit (R1 and V1 to V6 below) after the first freeze was lifted on green, and is frozen again
from that commit until the production fix passes it. After green, three of its failure messages
were reworded without changing any assertion (D1): they said a broken count or a missing
placeholder lands deep links off in every browser, but Chromium compensates through anchoring
while the exclusion is on (measured as B1), so they now name browsers without scroll anchoring.

Round 2 review: directed by the orchestrator on 2026-11-05. The check is revised again in its own
red commit (F3 item borders, F4 the generator reading `7 !important` as 7, N1 messages that print
the exact expected text, and F1 message corrections), frozen until the generator passes it.

Domain skills: none applicable. frontend-design: not applicable because nothing visible changes
once the cards render; the only visible difference is a taller loading placeholder. The
chrome-devtools MCP skills: not applicable because that server is not connected this session; the
drives use the scratch Playwright Chromium from earlier runs. No framework, API, data, payments, or
email skill fits a static site.

## Measured before (origin/main 1fc42e2, Playwright Chromium, `projects.json` held 1500 ms)

Probe: `scratchpad/issue40/probe40.py`, output in `scratchpad/issue40/base_probe.txt`.

| Case | 375x812 | 1440x900 |
| --- | --- | --- |
| `/#contact`: top of `#contact` minus header bottom after cards | 2063.23 px FAIL | 942.95 px FAIL |
| `/#contact`: CLS | 0.9237 | 0.6092 |
| `/#services`: offset after cards | 0.48 px PASS | 0.19 px PASS |
| No hash, wheel-scrolled to `#contact` during the hold: `#contact` moves | 104 -> 2167 FAIL | 259 -> 1202 FAIL |
| Cold load, no hash, CLS (held 0 ms and 1500 ms) | 0.0000 | 0.0002 (nav font swap) |

The grid grows from the 107 px loading line to exactly `rows x (card height + 30)`: 2170 at one
column (7 x 310), 1050 at three (3 x 350). 2170 - 107 = 2063 and 1050 - 107 = 943, the issue's
numbers. `#services` sits above the portfolio and does not move; the 26 px seen in the issue #31
drive does not reproduce on main today. Cold-load CLS with no hash is already about zero because
the portfolio is below the fold at load; the CLS cost is real only on a deep link or a scrolled
page, where it is 0.6 to 0.9.

## Why Chromium's scroll anchoring does not hold the position

Measured in `scratchpad/issue40/anchorctl2.py` (output `anchorctl2.txt`). Inserting 500 px into
`#github-projects` with `#contact` at viewport top 0 is fully compensated (scrollY +500, `#contact`
stays at 0). With `#contact` at 63, where `scroll-margin-top` puts every fragment target, nothing is
compensated. The fixed header covers the viewport's top 63 px, but anchor selection uses the whole
viewport, so the strip under the header shows `#portfolio`'s 80 px bottom padding. `.container` is
fully above the viewport, so Chromium selects `#portfolio` itself as the anchor, and `#portfolio` is
the element that grows: its top does not move, so there is nothing to compensate. This is
spec-correct behavior. It is not `html, body { height: 100% }` (setting `height: auto` changes
nothing), not `scroll-behavior`, not the nav, not `scroll-margin-top`, and not the fragment anchor
(the load event fires at about 250 ms, long before the fetch resolves, so Chromium has stopped
re-applying the fragment by then).

Excluding `#portfolio` from anchor selection with `overflow-anchor: none` makes Chromium pick
`#contact` instead. Prototyped by injection (`proto_anchor.txt`): every case above passes at both
widths, including the error and empty states, CLS on `/#contact` drops to 0.0013 / 0.0003.

## Options considered

1. **`overflow-anchor: none` on `#portfolio` alone.** One CSS line and every criterion passes in
   Chromium. But it works only where scroll anchoring exists: Chromium and Firefox. Safari has not
   shipped scroll anchoring, so on an iPhone, the most likely 375 px visitor, the deep link stays
   2063 px off. Could not be measured here: Playwright's WebKit build needs `libevent-2.1-7t64`,
   which needs sudo to install.
2. **Re-scroll after render when the hash names a later section and the visitor has not scrolled.**
   Fixes deep links in every browser but does nothing for criterion 2 (no hash, visitor scrolled),
   and needs "has the visitor scrolled" state that has to coexist with the issue #33 focus code.
3. **Reserve the grid's final height while loading (chosen), plus option 1 as the fallback.** The
   card height is fixed (320 px, 280 px at 768 and below) and every row is card height plus a 30 px
   gap, so the final height is computable from the card count and the column count alone. The
   placeholder is the loading line itself, which the renderer replaces on every exit path, so the
   reservation cannot outlive the loading state: no gap after an error, an empty file, or a
   success. With JavaScript off no loading line is written, so nothing is reserved. Option 1 then
   covers what reservation cannot: the error and empty states, where the reservation must collapse,
   a card count that drifted, and a browser without CSS `round()` (Chrome 125, Firefox 118, Safari
   15.4), where the declaration is invalid and `min-height` falls back to `auto`.

Prototyped by injection (`proto_both.txt`): all C1 and C2 cases pass, error and empty deep links
stay within 0.3 px. Its CLS figures on `/#contact` are an artifact of injecting the style at
DOMContentLoaded, after the first fragment scroll; Phase 4 measures the real stylesheet.

Known residual: in Safari only, the error and empty states still move a deep-linked `#contact` up
by the collapsed reservation, because there is no scroll anchoring to fall back on. Those states
are rare and the target lands above its spot rather than 2000 px below it.

## Acceptance criteria

From the issue, verbatim, with the checkable form under each.

1. Loading `/#contact` and `/#services` with `projects.json` delayed by 1500 ms leaves the target
   section's top within 2 px of the sticky header's bottom after the cards render, at 375 and 1440.
   Checkable: `probe40.py` C1 lines PASS at 375x812 and 1440x900 for both fragments.
2. Without a hash, rendering the portfolio does not move content the visitor has scrolled to.
   Checkable: `probe40.py` C2 lines PASS (wheel-scrolled to `#contact` during the hold, `#contact`
   moves at most 2 px), plus cold-load CLS with no hash stays at or below the baseline 0.0002.
3. The issue #33 focus behavior and Lighthouse accessibility and SEO 100 on `index.html` are
   unchanged. Checkable: adapted `drive33c.py` and `hist33.py` report the same PASS set as on
   main; Lighthouse 12 accessibility 100 and SEO 100 against a server on a free port.
4. All six verifiers pass. Checkable: each exits 0.

Added by this plan, from the orchestrator's constraints:

5. The reserved height equals the rendered grid's height at every breakpoint the grid uses.
   Checkable: at widths 375, 768, 769, 800, 992, 993, 1200, 1440, the `.portfolio-loading` box
   height during the hold equals `#github-projects`' height after render within 1 px.
6. No large blank gap in the error or empty state, or with JavaScript off. Checkable: `#portfolio`
   height in the error and empty states and with JavaScript off is within 5 px of main's.
7. A card count that no longer matches `projects.json` fails the gate, and
   `tools/build_projects.py` prints a WARN naming the exact `--portfolio-cards: N` line in
   `css/style.css` whenever the count it writes differs from the stylesheet's, without editing
   the stylesheet.

## Files that change

- `css/style.css`, portfolio section only:
  - `#github-projects` declares four custom properties: `--portfolio-cards: 7` (the number of
    entries in `projects.json`), `--portfolio-cols: 3`, `--portfolio-card-height: 320px`,
    `--portfolio-row-gap: 30px`, each with a short comment.
  - `.portfolio-item` takes `flex: 0 0 calc(100% / var(--portfolio-cols))`, the same for
    `max-width`, and `padding: 0 15px var(--portfolio-row-gap) 15px`.
  - `.portfolio-card` takes `height: var(--portfolio-card-height)`.
  - The `@media (max-width: 992px)` block sets `#github-projects { --portfolio-cols: 2; }` instead
    of the `.portfolio-item` flex and max-width. The `@media (max-width: 768px)` block sets
    `--portfolio-cols: 1` and `--portfolio-card-height: 280px` on `#github-projects` instead of the
    `.portfolio-item` flex and max-width and the `.portfolio-card` height; its `.portfolio-content`
    and `.portfolio-title` rules stay. Same two media queries, same widths: the reservation and the
    layout read the same variables, so they cannot disagree at any breakpoint.
  - `.portfolio-loading` gains `flex: 0 0 100%` and
    `min-height: calc(round(up, var(--portfolio-cards) / var(--portfolio-cols), 1) * (var(--portfolio-card-height) + var(--portfolio-row-gap)))`,
    with a comment saying why the placeholder carries the grid's final height, that every exit
    path of the renderer replaces it, and that where `round()` is unsupported the value, which
    holds `var()`, is invalid at computed-value time and `min-height` falls back to `auto`.
  - `#portfolio:has(.portfolio-loading, .portfolio-status)` gets `overflow-anchor: none`, with a
    comment carrying the anchor explanation above in two or three sentences. (Round 1 departure:
    the first version put it on `#portfolio` itself, permanently. Review measured that this takes
    the anchor away from a visitor reading the cards: 200 px added inside `#about` moved the card
    under the viewport middle 200 px, reflowed paragraphs moved it 156 px at 375 and 78 at 1440,
    and a 375x812 to 812x375 rotation sent it to -1125, against 0 and still visible on main.
    Scoped with `:has()` to the placeholder and the status rows, all of those match main, and the
    error and empty deep links still land within 0.23 px. Scoped to the placeholder alone, the
    error and empty deep links jumped by -592 and -225 px, because the exclusion lifts in the same
    frame the reservation collapses. A browser without `:has()` drops the rule and keeps normal
    anchoring.)
- `tools/build_projects.py`, also: the "Wrote" line prints `OUTPUT.name` instead of
  `OUTPUT.relative_to(ROOT)`. Unplanned: the gate's offline run of `main()` points `OUTPUT` at a
  temporary file, and `relative_to(ROOT)` raises on a path outside the repository. A normal run
  prints the same text.
- `index.html`: no change. The renderer already writes `.portfolio-loading` first and replaces it
  on success, empty, and error. Verified, not edited.
- `tools/verify_portfolio.py`: one new check, `check_grid_reserves_its_final_height`, registered in
  `main()` with the others and described in the module docstring. Narrow source assertions over
  `css/style.css` with comments stripped (reuse `without_comments`) and `index.html`:
  1. `--portfolio-cards: N` is declared exactly once, as an integer, and N equals
     `len(projects.json["projects"])` (reuse `load_projects`). The message names both numbers and
     says to update the stylesheet after regenerating.
  2. The top-level `.portfolio-loading` rule's `min-height` is exactly the reservation formula
     with whitespace removed, and no other rule sizes `.portfolio-loading` (its `::after`
     spinner excluded). The other three variables are declared on the top-level
     `#github-projects` rule. (Departure: pinned exactly rather than "references all four
     variables", because a formula that names all four and multiplies where it should divide
     passes the looser test.)
  3. The base `.portfolio-card` `height` and `.portfolio-item` `flex`, `max-width`, and `padding`
     are pinned exactly (whitespace removed, a trailing `!important` tolerated) on the top-level
     rule with exactly that selector, and no other rule, in any context, sets a height, margin, or
     box-sizing on a card, or those plus a padding, border, flex, or width on an item;
     `#github-projects` sets no `gap`. (Round 2: item borders added, because an item's height is
     its card plus padding plus border. A card border is not checked: the card's height is fixed
     and its box-sizing, which would make a border add, is checked.) Every pinned value, the
     reservation formula, the anchor selector, and the renderer pattern are printed as written in
     the failure message, so a legitimate reformat is a one-line fix. The four grid variables are set only on rules whose selector is exactly
     `#github-projects` (any media context), and the three besides the count have a top-level base
     value. (Round 1 departure: the first version checked only that item and card values mentioned
     a variable, which passed `calc(50% / var(--portfolio-cols))`, an extra 10 px of padding, a
     child override of a variable, and a height on an item.)
  4. The only `overflow-anchor` declaration anywhere in the stylesheet is `none`, `!important`
     tolerated, on the top-level `#portfolio:has(.portfolio-loading, .portfolio-status)` rule. A
     permanent exclusion on `#portfolio`, `html { overflow-anchor: none }`, or an `auto` override
     elsewhere all FAIL. Custom property names are compared case-sensitively, and the renderer's
     `loadPortfolio()` call is found with a whitespace-tolerant pattern that also accepts `void`.
  5. The renderer in `index.html` still writes a `portfolio-loading` element as the container's
     initial content.
  6. The generator warns: call `build_projects.stylesheet_card_count_warning` (via the existing
     `import_generator`) with a matching count and stylesheet text and assert `None`; with a
     mismatched count and assert a string naming `--portfolio-cards: <new count>` and
     `css/style.css`; with no declaration, a commented-out one, or two, and assert a warning.
     Then prove `main()` is wired to it by running the real `main()` offline: swap
     `fetch_repos`, `probe`, `OUTPUT`, and a new `STYLESHEET` module constant for temporary
     stand-ins, assert the WARN appears on stderr when the stylesheet's count differs from the
     one card written and not when it matches, and assert the stylesheet is byte-identical
     afterward. (Departure: a source scan for the name would pass on a call whose result is
     discarded or a name in a comment; running `main()` cannot.)
  Each failure message says what the visitor sees when it breaks. The docstring states the limits:
  it does not compute a height, does not know the column breakpoints are the right ones, and the
  browser drive is the proof that the reservation matches the render.
- `tools/build_projects.py`: a function, `stylesheet_card_count_warning(count, css_text)`, that
  returns `None` when `css_text` (comments stripped) declares `--portfolio-cards: <count>` and
  otherwise a warning string naming the exact line to change, for example
  `WARN  css/style.css declares --portfolio-cards: 7 but projects.json now has 8 cards; change it to --portfolio-cards: 8 or deep links below the portfolio land a row off`.
  A stylesheet with no declaration, or more than one, also returns a warning that says so.
  `main()` calls it after writing `projects.json`, with the count it wrote and the text of
  `STYLESHEET` (a module constant naming `css/style.css`, so the gate can point it elsewhere), and prints any warning to stderr like the other WARN lines. It never writes
  the stylesheet. Standard library only, like the rest of the script.
- `CLAUDE.md`: in "Portfolio Loading", one paragraph on the reservation and the anchor exclusion
  and why each exists; in "Updating Portfolio Content", a step: when the number of cards changes,
  update `--portfolio-cards` in `css/style.css`, and `verify_portfolio.py` fails until it matches;
  in "Verifying the portfolio data criteria", the new check in the criteria sentence. Stated as
  rules, not figures, apart from the variable name.
- `docs/superpowers/plans/2026-11-05-issue-40-deep-links-below-portfolio.md`: this file.

## Order of work

1. Commit this plan alone after approval.
2. Red: add `check_grid_reserves_its_final_height` and run `verify_portfolio.py` on the unchanged
   stylesheet; it must FAIL (no `--portfolio-cards`). Freeze it in `.claude/fix-lock` (honored by
   hand: the repo has no edit-guard hook). Record the red output. Commit as
   `test: require the portfolio grid to reserve its final height (issue 40)`.
3. Green: the `css/style.css` changes and the `build_projects.py` warning. Run all six verifiers. Commit as
   `fix: reserve the portfolio grid's height and keep it out of scroll anchoring (issue 40)`.
4. Mutations (below), each applied to a scratch copy or reverted with `git checkout` afterward;
   record each verdict.
5. Browser drive, before (origin/main) and after (branch), on separate free ports; never 8000.
6. CLAUDE.md, commit as `docs: describe the portfolio height reservation (issue 40)`.

## Mutations for Phase 4 (each must turn the named check red)

Source check, `verify_portfolio.py`:

- M1 `--portfolio-cards: 6` and M2 `: 8` (count drift) -> FAIL criterion 1.
- M3 a second `--portfolio-cards: 7` declaration inside a media query -> FAIL (exactly once).
- M4 the declaration only inside a CSS comment -> FAIL (comments stripped).
- M5 `--portfolio-cards: 7px` or `7.0` -> FAIL (integer).
- M6 `.portfolio-loading` loses its `min-height` -> FAIL; M7 its `min-height` drops
  `var(--portfolio-cards)` for a literal `2170px` -> FAIL.
- M8 `.portfolio-card { height: 320px }` restored -> FAIL; M9 the 768 block regains
  `.portfolio-card { height: 280px; }` -> FAIL.
- M10 the 992 block regains `.portfolio-item { flex: 0 0 50%; max-width: 50% }` -> FAIL;
  M11 `.portfolio-item` padding back to the literal `30px` -> FAIL.
- M12 `overflow-anchor: none` removed, M13 moved into a comment, M14 moved to `#contact` -> FAIL.
- M15 the renderer's initial `innerHTML` writes `portfolio-status` instead of `portfolio-loading`
  -> FAIL.
- M16 the min-height moved to a different selector (`.portfolio-loading-x`) -> FAIL.
- M18 `stylesheet_card_count_warning` always returns `None` (the warning removed) -> FAIL
  check 6; M19 it returns a warning that omits the new count -> FAIL; M20 `main()` no longer
  calls it -> FAIL.
- Round 1: R1a the exclusion back on plain `#portfolio`, R1b the scoped rule plus a permanent
  `#portfolio` copy, R1c scoped to `.portfolio-loading` alone -> FAIL check 4. V1 a child override
  of each variable (`.portfolio-item { --portfolio-cols: 4 }`, `.portfolio-loading
  { --portfolio-card-height: 0px }`, the 992 block written on `.portfolio-item`) -> FAIL. V2
  `.portfolio-item { height: 400px }`, padding `40px 15px var(--portfolio-row-gap) 15px`, flex
  `calc(50% / var(--portfolio-cols))`, an item or card margin, `#github-projects { row-gap }` ->
  FAIL. V3 `html { overflow-anchor: none }`, `.one-page-section { overflow-anchor: auto
  !important }` -> FAIL. V4 controls that must PASS: `!important` on the scoped rule and on the
  `min-height`, the `loadPortfolio();` call re-indented or written `void loadPortfolio();`, and an
  unrelated `--Portfolio-Cards: 1` (custom properties are case-sensitive). V6
  `--portfolio-cards: 07` must PASS the gate and must not make the generator warn.
- Round 2: F3 `.portfolio-item { border-bottom: 40px solid transparent }` -> FAIL. F4 the
  generator no longer stripping a trailing `!important` -> FAIL; `--portfolio-cards: 7 !important`
  in the stylesheet -> PASS (control).
- Control: the unmutated branch passes, and M17 a cosmetic change (reflowing whitespace inside the
  `min-height` value) still passes, so the check is not matching on formatting.

Browser, `probe40.py` plus the width sweep:

- B1 `--portfolio-cards: 6` with `overflow-anchor` kept: C1 still passes in Chromium through
  anchoring, which proves the fallback; B2 the same with `overflow-anchor` removed: C1 FAILs by one
  row, which proves the reservation is what carries Safari.
- B3 `overflow-anchor` removed, count right: success-path C1 passes, error and empty deep links
  move by the collapsed reservation, which proves why the fallback exists.

## Risks

- The `.portfolio-item` refactor from `33.333%` to `calc(100% / 3)` changes the column width by a
  few thousandths of a pixel. Screenshot the rendered grid at 375, 800, and 1440 before and after
  and compare card boxes; any difference over 1 px is a defect.
- The anchor exclusion changes what Chromium anchors to while `#portfolio` holds the placeholder
  or a status row. The first version applied it permanently and claimed that only mattered in the
  collapse cases; review (finder2 F2) showed that was false, because after render a visitor
  reading the cards then had no anchor and any height change above the section moved them. It is
  now scoped with `:has()`, so once the cards render anchoring is exactly main's. One consequence
  to accept: in the error and empty states the exclusion stays, so a visitor looking at the
  portfolio heading with `#contact` also in view keeps `#contact` fixed and the heading moves.
  The status row is a single line, so there is little to read there. Rare state, rare view.
- A visitor who zooms text only (minimum font size) does not change px heights; the card height is
  fixed px and its content is clipped, so the reservation still matches.
- The riskiest step is the source check's precision: earlier runs found checks that passed
  vacuously. The mutation list above is the guard; anything that survives a mutation is fixed
  before review.
- Not done: changing the generator to write the count into the stylesheet. That would make a
  generated-data script edit a hand-authored file; the gate catching drift is enough.

## Proof

| Criterion | Proof |
| --- | --- |
| 1 | `probe40.py` C1, before and after, 375 and 1440, `#contact` and `#services` |
| 2 | `probe40.py` C2 before and after, plus cold-load CLS with no hash |
| 3 | adapted `drive33c.py` and `hist33.py`, same PASS set as main; Lighthouse 12 accessibility and SEO 100 |
| 4 | the six verifiers' exit codes and final lines |
| 5 | width sweep: reserved height vs rendered grid height at 375, 768, 769, 800, 992, 993, 1200, 1440 |
| 6 | `#portfolio` height in error, empty, and JavaScript-off states, before and after |
| 7 | mutations M1 and M2; the generator WARN via check 6 and mutations M18 to M20 |

Red proof for the rewritten test, run in a scratch worktree at the merge base 1fc42e2 with only
the rewritten `tools/verify_portfolio.py` applied (`scratchpad/issue40/red2_portfolio.txt`): exit
1, 15 FAILs, every one a missing feature, ending at "tools/build_projects.py defines
stylesheet_card_count_warning". The main-run checks are not reached there, so two partial
generators on the same tree show they fail for the right reason: with the helper alone
(`red2_fn_only.txt`) the only new FAIL is the missing `STYLESHEET`; with the helper and
`STYLESHEET` but no call in `main()` (`red2_no_wiring.txt`) the only new FAIL is "main() warns
when the stylesheet says 7 and it writes 1 card", while "stays quiet when the stylesheet says 1"
passes, which shows the fetcher now yields exactly 1 card.

The issue #31 drives (`impl/drive.py`, `impl/drive2.py`, adapted copies in `issue40/`) run before
and after with the same PASS set; `drive2.py` covers the empty and error states at 375, 767, 768,
and 1440. The live drive must show `#contact` within 2 px of the header bottom after the cards
render at both widths, and the error state's deep link within 2 px in Chromium.

Round 1 proof (Chromium, base origin/main vs branch, `scratchpad/issue40/r1/`): finder2's
reading-the-cards scenarios now match main. 200 px added inside `#about` moves the card under the
viewport middle 0 px on both, paragraph reflow 0 on both, and the 375x812 to 812x375 rotation
keeps "QuakeGlobe" visible on both. In the error and empty states, 200 px added above with
`/#portfolio` deep-linked moves the heading 0 on both. `probe40.py` still passes C1 and C2 at both
widths, and the error and empty `/#contact` deep links land within 0.23 px. The width sweep still
shows 0 px difference at every width.
