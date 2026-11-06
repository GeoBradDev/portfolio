# Plan: Hero subtitle and photo credit fail WCAG contrast over the background photo (issue #34)

Risk tier: Medium. Nothing forces High. It starts at Low and raises twice: the defect is
text over a photograph, which no source-level check and neither axe nor Lighthouse can
measure, so the real proof is pixels in a browser at several widths; and it alters existing
behavior (the look of the hero, the first thing every visitor sees) rather than adding. The
diff is small: three CSS rules, one regenerated image, one verifier check, docs.

Approval: approved 2026-11-05 by the orchestrator on the owner's behalf, recommended option
(scrim 0.5, subtitle #f2f2f2, credit #fff on rgba(0, 0, 0, 0.55) with an underlined link, share
card regenerated with SCRIM 0.5 and subtitle fill (242, 242, 242)). The reviewer looked at the
side-by-side at 1440x900 and judged it a modest darkening within the issue's own recommended fix.

Domain skills:
- superpowers:test-driven-development: invoke. The new verifier check is written and run red
  against the current CSS before the CSS changes, and the browser measurement below is run
  red against `origin/main` (796dcca) before the fix.
- superpowers:verification-before-completion: invoke before any success claim.
- frontend-design:frontend-design: invoke for the restraint check only. This is a visible
  change to the hero; the brief is the smallest change that clears the thresholds, not a
  redesign.
- chrome-devtools-mcp:a11y-debugging: not applicable because its MCP server failed to
  connect this session; the measurement runs in Playwright Chromium instead.
- Every other listed skill (Django, Expo, React, FastAPI, data viz): not applicable because
  this is a static HTML and CSS site.

## Background: where the code is now

Issue #31 rewrote `css/style.css`, so the issue's line numbers are stale. On `origin/main`
(796dcca):

- `.home-1:after` (css/style.css ~785): the only treatment over the photo, a flat
  `background-color: rgba(0, 0, 0, 0.4)`.
- `#home .typer-title` (~863): `color: #bfbfbf`, 22px (26px from 768px up), computed weight
  700 in Lato. 22px bold is large text under WCAG (18.66px bold or more), so the threshold is
  3:1.
- `#credit` (~1778): `color: #070606`, 16px, `font-weight: 1000`. CSS Fonts 4 accepts
  1000, but no Lato face loaded here is heavier than 700, so it renders as the bold that is
  already there; the issue asks for it gone, and the new white-on-dark credit reads better
  at the body weight. No background. 16px normal text, so
  4.5:1. Its link (`#credit a`) inherits the color and `a { text-decoration: none }` at
  css/style.css ~242 removes the underline, so the link differs from the surrounding text
  by nothing at all (SC 1.4.1).
- `index.html` ~207: `<div id="credit"><p>Photo by <a ...>Matthew McFarland</a></p></div>`
  inside `#home`. The markup does not change.
- `tools/make_og_card.py` mirrors the scrim (`SCRIM = 0.4`) and draws the subtitle line in
  `(233, 233, 233)`. Running it unchanged on this machine reproduces `img/og-card.jpg`
  byte for byte (checked: `cmp` identical), so a regeneration changes only what the edit
  changes.

## Measurement method (used before and after)

Script: `scratchpad/issue34/measure.py`, Playwright Chromium, served by
`python3 -m http.server` on 127.0.0.1:8734. For each viewport and each text (subtitle,
credit paragraph, credit link):

- **bg**: screenshot of the element's own box with its text color set to `transparent`.
  Everything else stays painted: the photo, the scrim, any element background, any
  text-shadow. This is the composited surface under the glyphs.
- **mask**: the same box with the text painted `#ff00ff` and no shadow. A pixel is a glyph
  pixel when it differs from bg by more than 60 in summed RGB.
- Contrast is the WCAG ratio of the computed text color (alpha composited over the pixel
  if translucent) against each bg pixel.
- Reported: **glyph min**, the ratio against the brightest pixel under any glyph (the
  acceptance criterion), and the issue's method over the whole text box (p5 / median / p95,
  and the share under threshold).
- Viewports: 375x812, 375x667, 1280x800, 1440x900, 1920x1080, 2560x1440. Each serves the
  file its breakpoint names (hero-1280.webp up to 1280, hero-1920.webp to 1920,
  hero-2560.webp above; confirmed from the computed `background-image`). Every viewport is
  run a second time with `.home-1 { background-image: url('/img/hero-1280.jpg') !important }`
  injected, which is what a browser failing the `@supports` test paints.

### Before (origin/main, 796dcca)

| Text | Viewport | Need | Glyph min | Glyphs under | Box p5 / med / p95 | Box under |
|---|---|---|---|---|---|---|
| Subtitle | 375x812 | 3.0 | 1.56 | 40.5% | 1.82 / 3.65 / 8.87 | 38.7% |
| Subtitle | 375x667 | 3.0 | 1.55 | 24.8% | 1.95 / 4.57 / 9.01 | 26.7% |
| Subtitle | 1280x800 | 3.0 | 1.55 | 24.5% | 1.98 / 4.53 / 8.62 | 25.7% |
| Subtitle | 1440x900 | 3.0 | 1.56 | 35.3% | 1.75 / 4.19 / 8.78 | 34.2% |
| Subtitle | 1920x1080 | 3.0 | 1.55 | 52.3% | 1.65 / 2.97 / 8.54 | 50.7% |
| Subtitle | 2560x1440 | 3.0 | 1.55 | 57.6% | 1.68 / 2.87 / 8.56 | 52.4% |
| Subtitle, JPEG | 375 to 2560 | 3.0 | 1.56 to 1.58 | 24.7 to 56.6% | | |
| Credit | 375x812 | 4.5 | 1.32 | 55.1% | 1.22 / 3.59 / 6.67 | 61.5% |
| Credit | 1440x900 | 4.5 | 1.20 | 41.0% | 1.46 / 4.64 / 6.86 | 47.5% |
| Credit | 1920x1080 | 4.5 | 1.14 | 58.0% | 1.26 / 3.50 / 6.84 | 60.3% |
| Credit | 2560x1440 | 4.5 | 1.18 | 68.1% | 1.31 / 3.32 / 6.85 | 62.4% |
| Credit link | 375x812 | 4.5 | 1.32 | 53.6% | | |
| Credit link | 1440x900 | 4.5 | 1.20 | 43.6% | | |
| Credit, JPEG | 375 to 2560 | 4.5 | 1.08 to 1.27 | 40.9 to 70.5% | | |

This reproduces the issue (its 375 and 1440 rows agree within a few hundredths). The full
table is `scratchpad/issue34/before/results.json`.

### The finding that decides the design

The brightest pixel behind the subtitle composites to relative luminance about 0.32 at
every viewport and in both formats. That is `0.6 * 255`: a pure white sun glint under the
40 percent scrim. The worst case is therefore not a property of one crop of one file. It is
the brightest value any photo pixel can have, so it can be computed in closed form from the
scrim alone:

- worst background under the subtitle = white under the scrim = `255 * (1 - scrim)` gray.
- At scrim 0.4 that is `#999999`. Even `#ffffff` text reaches only 2.84:1 against it. **No
  text color alone can meet 3:1 under the current scrim.** Something has to darken what is
  under the glyphs.

A text-shadow was considered and rejected: under the glyph interior a blurred shadow's
opacity depends on stroke width, blur radius, and font rendering, so it cannot be bounded
from the source, and the verifier could not pin it. A local backing on the subtitle alone
(a pill or band) was rejected as a bigger visual change than the issue's recommendation. A
vertical gradient scrim was rejected because the subtitle's vertical position moves with
viewport height, so proving the dark band covers it at every size needs a browser, not a
computation. A small flat increase to the existing scrim is the smallest change whose
worst case is provable from the CSS alone.

## The change

1. `.home-1:after`: `rgba(0, 0, 0, 0.4)` to `rgba(0, 0, 0, 0.5)`.
2. `#home .typer-title`: `color: #bfbfbf` to `color: #f2f2f2`. Kept a step off the h1's
   `#fff` so the hierarchy survives. Worst case: `#f2f2f2` on `#808080` (white under 0.5) is
   **3.53:1**, against 3:1.
3. `#credit`: drop `font-weight: 1000`; `color: #070606` to `color: #fff`; add
   `background: rgba(0, 0, 0, 0.55)`, `padding: 2px 8px`, `border-radius: 3px 3px 0 0`
   (it sits flush on the hero's bottom edge, so only the top corners round). Worst case:
   white under the 0.5 scrim and then the 0.55 backing composites to `#3a3a3a`
   (`255 * 0.5 * 0.45`), and `#fff` on that is **11.4:1**, against 4.5:1. Note the credit
   alone, without the scrim under it, would be 4.2:1 against a raw white pixel; the scrim is
   part of its proof and the verifier composites both.
4. `#credit p { margin: 0 }`, so the backing hugs the line instead of carrying the global
   `p { margin: 0 0 10px }` as dead dark space under the text.
5. `#credit a { text-decoration: underline }`. The link keeps the inherited `#fff` and is
   told apart by the underline, which does not rely on color (SC 1.4.1). The existing
   `.home-1 a:focus-visible { outline-color: #fff }` ring keeps working on the dark backing.
6. `tools/make_og_card.py`: `SCRIM = 0.5`, and the subtitle line's fill from
   `(233, 233, 233)` to `(242, 242, 242)` so the card still mirrors the hero. Regenerate
   `img/og-card.jpg`: previewed at 1200x630, **161.4 KB** (was 175.0 KB), under the 200 KB
   budget.

### Preview of the change (CSS injected over origin/main, same script)

| Text | Viewports | Need | Glyph min, WebP | Glyph min, JPEG | Glyphs under |
|---|---|---|---|---|---|
| Subtitle | 375x812, 375x667, 1280, 1440, 1920, 2560 | 3.0 | 3.58 at every one | 3.58 to 3.63 | 0% |
| Credit | same | 4.5 | 11.55 at every one | 11.55 | 0% |
| Credit link | same | 4.5 | 11.55 at every one | 11.55 to 11.57 | 0% |

The measured subtitle minimum (3.58) sits just above the closed-form 3.53, as it should: the
brightest real pixel is a hair under pure white. The closed form is the floor.

An alternative with less darkening, scrim 0.45 and subtitle `#fff`, measured 3.36 minimum
(closed form 3.37). It loses the h1/subtitle color step and has less margin, so it is not
the recommendation, but it is a one-line swap if the owner prefers a brighter photo.

## Acceptance criteria

From the issue, verbatim, with the measured target in brackets:

- [ ] The photo credit, including the link, reaches at least 4.5:1 against its backing at
  375px and 1440px. [Measured at all six viewports and the JPEG fallback, glyph min.]
- [ ] The subtitle reaches at least 3:1 against the brightest pixel behind its glyphs at
  375, 1280, 1920, and 2560px viewports. [Plus 1440 and 375x667, and the JPEG fallback.]
- [ ] The credit link is distinguishable from surrounding text without relying on color.
  [Underlined; computed `text-decoration-line` of `#credit a` is `underline`.]
- [ ] `tools/verify_seo_a11y.py` checks both colors, and all six verifiers pass.

Added by this plan:

- [ ] `img/og-card.jpg` regenerated from the updated script, 1200x630, under 200 KB, and
  the script's `SCRIM` equals the CSS scrim (the verifier asserts the match).
- [ ] Lighthouse accessibility and SEO stay 100 on `index.html`.
- [ ] No regression in the hero, nav, or layout at 375 and 1440 (screenshots before and
  after; only the scrim, subtitle, and credit pixels differ).

## Files that change

- `css/style.css`: `.home-1:after`, `#home .typer-title`, `#credit`, new `#credit p` and
  `#credit a` rules beside `#credit`; the "40 percent scrim" sentence in the `@supports`
  comment becomes "50 percent". A short comment on the scrim rule says it is load-bearing
  for the subtitle's contrast and names the verifier.
- `tools/verify_seo_a11y.py`: new `check_hero_text_contrast()`, called from `main()`, and
  the `check_focus_ring_contrast` docstring's "40 percent scrim" wording.
- `tools/make_og_card.py`: `SCRIM`, the subtitle fill, docstring "rgba(0, 0, 0, 0.4)".
- `img/og-card.jpg`: regenerated.
- `tools/optimize_images.py`: comment "40 percent black scrim" to 50 (comment only).

Departure, made while implementing: every comment and doc sentence that named the scrim's
alpha ("40 percent scrim", `rgba(0, 0, 0, 0.4)`) and the share card's size ("175.0 KB") now
states the rule without the figure ("the scrim from `.home-1:after`", "the script's `SCRIM`
must equal the alpha in that rule"), instead of swapping 40 for 50 and 175.0 for 161.4. The
verifier pins the numbers, so prose that repeats them can only go stale. This applies to the
`@supports` comment in `css/style.css`, the `check_focus_ring_contrast` docstring, the
`make_og_card.py` docstring, the `optimize_images.py` comment, and both CLAUDE.md passages.
The credit and credit link lines in `check_hero_text_contrast()` extend the house format with
"and the backing" in the parenthetical, since their surface has two layers.
- `CLAUDE.md`: the Responsive Hero Background paragraph's "40 percent scrim", the share
  card section's `rgba(0, 0, 0, 0.4)` and "175.0 KB", the Accessibility section (one bullet
  on hero text contrast and why it is computed against white under the scrim), and the
  verify_seo_a11y description (hero text joins the computed contrast checks).

## Order of work

1. Write `check_hero_text_contrast()` in `tools/verify_seo_a11y.py` and run the verifier
   against the unchanged CSS. It must FAIL on: the subtitle (1.55:1, `#bfbfbf` on
   `#999999`); the credit (no backing declared, or `#070606` failing); the credit link (no
   underline); the og-card scrim match only if the script were already changed (it is not,
   so that check passes red-first and is proven by mutation instead, see Proof). Commit the
   red check alone with the failing output in the commit body.
2. CSS changes 1 to 5. Rerun: the verifier goes green.
3. `make_og_card.py` changes, then `python3 tools/make_og_card.py`; record its output line.
4. Docs and comments listed above.
5. Full gate, Lighthouse, browser measurement after, regression screenshots.

### check_hero_text_contrast(), specified

Reads `css/style.css` with comments stripped (`without_comments(..., "css")`), like
`check_text_contrast`.

- `HERO_WORST_PHOTO_PIXEL = "#ffffff"`, a module constant with a comment: the photo cannot
  be read from source, so the check measures against the brightest pixel any photo can
  contain; the Phase 1 browser measurement found the subtitle crossing sun glints at
  effectively pure white, so this is the real worst case, not a theoretical one.
- Scrim: parse `background-color: rgba(0, 0, 0, A)` from the `.home-1:after` rule. Fail if
  the rule is missing, the color is not black rgba, or A is not in [0, 1].
- Composite helper: `over(top_rgb, alpha, bottom_rgb)` per channel in sRGB 0-255, which is
  what browsers do for `background-color` layering (non-linear blending). Round to int and
  format as `#rrggbb` so the existing `contrast_ratio()` is reused.
- Subtitle: `color` of `#home .typer-title` via `declared_color`; also scan every rule whose
  selector list contains `.typer-title` (including inside `@media`) and fail if any other
  rule sets `color`, so a breakpoint override cannot slip past. Ratio against
  `over(black, A, white)` must be at least `HERO_LARGE_TEXT_MINIMUM = 3.0`, with the comment
  that it is 22px/26px at weight 700, large text.
- Credit: `#credit` must declare an opaque hex `color` and a `background` (or
  `background-color`) of black `rgba(0, 0, 0, B)`. Background = `over(black, B,
  over(black, A, white))`. Ratio at least `CONTRAST_MINIMUM` (4.5).
- Credit link: a `#credit a` rule must declare `text-decoration` (or
  `text-decoration-line`) containing `underline`; if any rule matching `#credit a` declares
  a `color`, that color is held to the same 4.5:1 against the same background.
- og card: parse `SCRIM = <float>` from `tools/make_og_card.py` and check it equals A, so
  the card cannot drift from the hero again.

Printed lines follow the house format: `"%s is %.2f:1 (%s on %s, white photo pixel under
the %.2f scrim), at or above %.1f:1"`.

## Risks

- **The whole hero gets 10 points darker.** That is the visible cost. Mitigated by keeping
  it flat (no new shapes on the photo) and by the screenshots for owner approval below.
- **The verifier proves the worst case only for black-rgba layers.** A future gradient or
  image scrim would fail the parse and force the check to be rewritten, which is the
  intended failure mode rather than a silent pass. Stated in the docstring.
- **sRGB vs linear compositing.** Chromium composites `background-color` layers in sRGB,
  which the helper mirrors; the browser measurement (3.58 measured vs 3.53 computed) is the
  cross-check that the model is not optimistic.
- **The credit box changes the credit's footprint** (padding plus no paragraph margin). It
  is absolutely positioned at `bottom: 0; right: 10px`, so nothing flows around it; the
  screenshots check it does not collide with the chevron at 375.
- **og-card regeneration.** Byte-identical reproduction was confirmed, so the new file
  differs only by the scrim and the subtitle fill.
- Not touched: issue #40 (deep-link offset), the nav link colors over the hero, and every
  other hero element.

## Proof

| Criterion | Proof |
|---|---|
| Credit and link at least 4.5:1 | `measure.py` after: glyph min per viewport, WebP and JPEG; verifier credit lines |
| Subtitle at least 3:1 on brightest pixel | `measure.py` after: glyph min at 375, 1280, 1920, 2560 (+1440, 375x667), WebP and JPEG; verifier subtitle line |
| Link distinguishable without color | computed `text-decoration-line: underline` on `#credit a` in the drive; verifier underline line; screenshot |
| verify_seo_a11y checks both, six verifiers pass | red run output (step 1), green full gate |
| Verifier catches regressions | mutation runs, each must FAIL: scrim back to 0.4; subtitle back to `#bfbfbf`; `#credit` background removed; underline removed; a `@media` rule setting `.typer-title` color `#bfbfbf`; `SCRIM = 0.4` in make_og_card.py |
| og card | `make_og_card.py` output line; verifier dimension and budget lines |
| Lighthouse | accessibility and SEO 100 on index.html (port other than 8000) |
| No regression | before/after full-viewport screenshots at 375x812 and 1440x900; nav sticky state after scroll unchanged |

Before screenshots: `scratchpad/issue34/before/webp-<vp>-hero.png` (and `jpeg-...`), side by
side with the preview at `scratchpad/issue34/compare-1440x900.png` and
`scratchpad/issue34/compare-375x812.png`.
