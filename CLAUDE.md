# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git exception for /work-issue

When executing the /work-issue workflow, Claude may run `git commit` and `git push`
on `issue-*` feature branches only. Never commit or push to the default branch, and
never commit or push outside a /work-issue run. The global no-commit policy applies
in all other circumstances.

## Project Overview

Static portfolio website for GeoBrad.dev (Brad Stricherz) - a geospatial software developer's personal site. Deployed to GitHub Pages at www.geobrad.dev.

## Technology Stack

- **Frontend**: Vanilla HTML5, CSS3, JavaScript (jQuery-based)
- **CSS Framework**: Bootstrap 3.x
- **Key Libraries**:
  - jQuery 3.7.1 (js/jquery.min.js)
  - Bootstrap JS 3.3.7 (js/bootstrap.min.js)
- **Deployment**: GitHub Pages with custom domain (CNAME)

Owl Carousel, Magnific Popup, Isotope, imagesLoaded, jQuery Typer, and Particles.js
were removed in issue #15. None of them had a matching element on any page, so all
of them downloaded and did nothing. Do not reintroduce a library without an element
that actually uses it.

The file shipped jQuery 2.2.4 for two years while this document claimed 3.x, which left
CVE-2020-11022, CVE-2020-11023, and CVE-2019-11358 open (issue #17). It is now 3.7.1, and
`tools/verify_security.py` asserts the version in the file against the version named here, so
the claim cannot drift again. Bootstrap 3.3.7 is the release that added jQuery 3 support; do
not downgrade one without the other.

Font Awesome is 4.7.0, served locally from `css/font-awesome.min.css` and `fonts/`, linked from
`index.html` and `resume.html`. `privacy.html`, `thanks.html`, and `404.html` carry `<link>` tags
but no `fa-` icons, so none of them links the stylesheet or needs it; do not add an icon to any of
them without adding the link. Every `fa` icon on the two pages that do use them carries
`aria-hidden="true"`, because the glyph is a CSS `::before` on an empty element and its Private
Use Area codepoint is announced as whatever the screen reader's character database says.
`tools/verify_seo_a11y.py` rejects one without it.
`resume.html` used to pull 6.5.1 from cdnjs, twice and without SRI, which meant two icon
majors, two syntaxes, and a third party on the critical path. Use bare `fa fa-*` classes; the
FA5/FA6 `fas`/`fab`/`far` style classes render nothing here and the verifier rejects them.

## Site Structure

- `index.html` - Main portfolio page with sections: home, about, services, portfolio, contact
- `resume.html` - Interactive resume with dark mode toggle
- `privacy.html` - Privacy policy page (160KB). A Termly-generated paste wrapped in a document
  shell added by issue #19. Before that it began at `<style>` with no doctype, `<html>`, `<head>`,
  or `<title>`, so it rendered in quirks mode with a guessed encoding. A regenerated policy
  replaces the content inside `<body>`; it does not replace the file, because the file is what
  carries the head.
- `thanks.html` - Contact form confirmation page. Standalone, no JavaScript.
- `404.html` - Served by GitHub Pages for any unmatched path. Standalone, no JavaScript, and
  carries its own copy of `thanks.html`'s four style rules rather than pulling in Bootstrap for
  one panel. Its favicon `href` is root-absolute, unlike every other page's: Pages serves this
  document at the URL that was requested, without redirecting, so a relative href resolves
  against the mistyped path.
- `robots.txt` - Allows everything and names the sitemap. Deliberately Disallows nothing; see
  the SEO section below for why.
- `sitemap.xml` - One entry, the homepage. The other four pages are noindex.
- `css/style.css` - Main custom styles
- `js/main.js` - Navigation, scroll, and skill-bar logic. Loaded by `index.html` only.
- `img/` - Images including profile photo, badges (Cesium certification, QR code), and
  `og-card.jpg`, the 1200x630 link-unfurl card
- `fonts/` - Font Awesome and Glyphicons
- `tools/` - Standalone dev-time Python scripts. The deployed site never runs them.

## Key Features & Architecture

### js/main.js

Loaded by `index.html` only; `resume.html` and `privacy.html` are standalone. It
drives the sticky navbar, on-page smooth scrolling, active-link tracking, mobile
nav collapse, the scroll-to-top button, and the skill bars.

Everything in it has a matching element in `index.html`. That is the rule the file
exists to keep: it once held 664 lines, roughly 500 of which targeted elements no
page contained, and the whole file went unloaded for two years without anyone
noticing (issue #16). Do not add a block here without an element that uses it, and
run `python3 tools/verify_interactivity.py` after touching `js/main.js` or the
markup it depends on.

Two invariants that are easy to break by accident:

- Skill bar widths come from `data-percent` on `.progress-bar-line`, never from an
  inline `style`. CSS starts the bars at 5% and JavaScript animates them to the
  target once the section scrolls into view. With JavaScript off the bars stay at
  5%; that is accepted, since the portfolio section already requires JavaScript.
- `navHeight()` subtracts an open `.navbar-collapse`. Below the Bootstrap
  breakpoint the expanded dropdown is in flow inside the fixed header, so measuring
  it raw returns 278px against the 63px it collapses back to, and every nav link
  then stops that far short of its target.

The hero has no parallax. `.home-1` uses `background-size: cover`, so shifting
`backgroundPosition` slides the image down and exposes blank space under the
overlay. The `parallax()` function and the `parallax` class were removed together.

`.portfolio-overlay` must keep `pointer-events: none`. It covers the whole card at
`z-index: 3` above the content at `z-index: 2`, and an `opacity: 0` element is
still hit-testable, so without it the overlay swallows every click and the "Live
Demo" and "Code" anchors become unreachable.

### Dynamic Portfolio Loading
The portfolio section in index.html (inline `<script>` before `</body>`, embedded styles further
down the same block) dynamically fetches and displays GitHub repositories:
- Fetches repos from multiple GitHub users: GeoBradDev, MapTheVoteSTL, Seaside-Sustainability-Web-GIS
- Filters repositories containing "portfolio" in description
- Cards are built with `document.createElement` and `textContent`, never a template literal, so
  a hostile repo `name` or `description` can only ever render as text
- `safeUrl()` gates the "Live Demo" and "Code" links: it accepts only an `https:` URL and returns
  `null` otherwise, and a `null` result means that link, or the whole-card click handler, does
  not render at all
- Embedded CSS in index.html for portfolio styling

### Navigation & Scrolling

Function names, not line numbers, because line numbers go stale.

- `stickyNav()` adds `.nav-sticky` past 100px and reveals `.scroll-up` past 1000px
- The `a.scroll` click handler animates to the target, honoring each link's
  `data-speed` and skipping the animation under `prefers-reduced-motion`
- `changeActiveNavLink()` highlights the link for the visible `.one-page-section`.
  A section without that class never highlights, which is how `#portfolio` was
  silently excluded before issue #16
- All three run from one `scroll` handler throttled to one pass per frame with
  `requestAnimationFrame`, and once on ready so a deep link or a reload partway
  down the page starts in the right state

### Contact Form
- Uses FormSubmit service (https://formsubmit.co/) - no backend required
- Form action points to encrypted FormSubmit email endpoint
- There is no client-side validation. The commented-out block that used to sit in `js/main.js` was deleted in issue #16; the form relies on the `required` attributes and FormSubmit.
- Two hidden fields carry the post-submit contract. `_next` is
  `https://www.geobrad.dev/thanks.html`; without it FormSubmit leaves the visitor on its own
  confirmation page and they never come back. `_subject` labels the mail. `verify_content.py`
  asserts `_next` is https, points at the host `CNAME` names rather than a hardcoded one, and
  names a page that exists in the repo, because a `_next` pointing at a 404 is worse than none.
  The URL has to be absolute for FormSubmit to honor it.
- FormSubmit's captcha is left on. It adds an interstitial before the redirect, not instead of it.
- The `#form-message` div and the `.name-error` / `.email-error` / `.message-error` spans were
  deleted in issue #18. Nothing had written to them since #16. They were dead as content but not
  weightless: each was `display: block` with `margin-top: 8px` plus `.mb-30`, inside floated grid
  columns where those margins could not collapse away, and removing them alone collapsed the form
  from 387px to 289px. `.input-field`'s `margin-bottom`, `textarea.input-field`'s `margin-bottom`,
  and `.submit-btn`'s `clear` now carry that spacing, and `verify_content.py` asserts all three.
  Do not move the pre-button gap onto `.submit-btn` as a `margin-top`: every field sits in a
  floated column, so the button's static position is the top of the form and `clear: both` turns
  any `margin-top` into clearance that absorbs it.
- Each field carries a `.sr-only` `<label for>` added in issue #19. The placeholders stay, but a
  placeholder is a hint rather than a name: it disappears the moment the field has content, which
  is exactly when someone tabbing back through a half-filled form needs to know what it holds.
  `.sr-only` is Bootstrap 3's and takes the label out of flow, so the form still measures 387.5px.
  `verify_seo_a11y.py` asserts every visible control is labelled and that the five FormSubmit
  field names are unchanged; the honeypot is exempt by shape, since labelling it would advertise
  it to the bots it exists to catch.

### Accessibility

The invariants issue #19 established. `tools/verify_seo_a11y.py` holds all of them.

- **The skip link is the first focusable element in `index.html`,** and targets `#about` rather
  than `#home` because the hero holds nothing to read. It is parked at `top: -100px` and pinned to
  `top: 12px` on focus, at `z-index: 200` so it clears `.nav-wrapper` at 20 and `.loader-con` at
  99. It styles `:focus`, not `:focus-visible`: the link is invisible until focused, so there is
  no mouse-click case to suppress.
- **`css/style.css` must never suppress the focus outline unconditionally again.** It set
  `outline: none` on `a, a:focus, a:hover, a:active` plus `.input-field` and `.submit-btn`, which
  left every keyboard user navigating blind. `:focus-visible` now carries the ring.
- **`a:focus:not(:focus-visible) { outline: none }` is load-bearing, not tidying.**
  `bootstrap.min.css` carries `a:focus { outline: 5px auto -webkit-focus-ring-color }` at the same
  (0,1,1) specificity, and `style.css` loads after it, so the deleted blanket suppression was the
  only thing holding it back. Without this rule a mouse click on any anchor paints a ring that
  stays until blur.
- **A focus ring's color has to suit the surface under it.** White over the hero and the
  transparent nav; `#232323` everywhere else, including the footer at `#f1f1f1` and the nav once
  `.nav-sticky` repaints it `#fff` past 100px of scroll.
- **Every icon-only control has an `aria-label` and every decorative icon has `aria-hidden`.** The
  two Bluesky links get neither: their `<img alt="Bluesky">` already names them, and a label would
  win over the alt and leave it dead.
- The contact items use `h3`/`h4`, not `h5`/`h6`. They sit under an `<h2>Contact</h2>`, so the old
  tags skipped two levels and failed Lighthouse's `heading-order`. The CSS pins 13px and 16px so
  the promotion changed no rendered size.

### SEO and indexing

Issue #19 added the head metadata every page was missing. Four rules that are easy to undo by
accident:

- **Every page carries a self-referencing canonical** on the host `CNAME` names, because the site
  answers on both `geobrad.dev` and `www.geobrad.dev` and without one those are two URLs for one
  page. `index.html` canonicalizes to the bare root, everything else to its own filename. The
  verifier reads the host from `CNAME`, so changing the custom domain fails the gate until the
  pages agree.
- **Only `index.html` is indexable.** `resume.html`, `privacy.html`, `thanks.html`, and `404.html`
  carry `noindex`, and `sitemap.xml` lists only the homepage; listing a noindex page in a sitemap
  asks a crawler to do two contradictory things.
- **Open Graph and Twitter tags live on `index.html` alone,** and the verifier asserts no other
  page carries an `og:url`. A card on a page nobody is meant to share is markup that can only go
  stale. `og:image` is absolute, because a crawler resolves a relative URL against its own base
  and silently ends up with no image.
- **The `Person` JSON-LD may only state what the page states.** Every field is something a visitor
  can read on `index.html`, which is why the employer named on `resume.html` is absent: the
  homepage never mentions it. Each `sameAs` profile must also be linked from the page, and the
  verifier checks that, so a profile the page later drops cannot go stale unnoticed.

### Visual Effects
- No parallax. See the `js/main.js` section above for why it was removed.
- Skill bars for the skills section, driven by `progressBars()`
- Hover effects and transitions throughout

### Responsive Hero Background
`.home-1` in `css/style.css` serves the hero through three viewport-width breakpoints,
not device pixel ratio. Keying on DPR would hand a 3x phone the 2560 file, which is
the opposite of what is wanted.

| Viewport | File | Size |
|---|---|---|
| up to 1280px | `img/hero-1280.webp` | 200.6 KB |
| 1281px to 1920px | `img/hero-1920.webp` | 398.1 KB |
| 1921px and up | `img/hero-2560.webp` | 683.6 KB |

The base `.home-1` rule declares only `url('/img/hero-1280.jpg')`. All three WebP
variants live inside one

```css
@supports (background-image: image-set(url('/img/hero-1280.webp') type('image/webp')))
```

block, with the two breakpoint `@media` rules nested inside it. A single test gates
both the syntax and the format, because every engine that parses `image-set()` with
`type()` also decodes WebP. Anything older never enters the block and keeps the JPEG.

Two rules for editing this:

- **Never declare a WebP URL outside the `@supports` block**, and do not reach for
  `-webkit-image-set()`. The prefixed form cannot express a format fallback, so
  Safari 6 to 13, which support the prefixed function but not WebP, resolve it to a
  file they cannot decode and paint no hero at all, only the 40 percent scrim from
  `.home-1:after`. Safari 14 to 16 also land on the JPEG under this structure. That
  is the accepted cost of never handing any browser an undecodable file.
- The JPEG stays a plain `url()` in the base rule, so it is the universal floor.

`index.html` preloads the matching variant per breakpoint, because a CSS background
image is not discovered until the stylesheet parses, and this one is the LCP element.
Two details matter:

- The preload `href` values are root-absolute to match the URLs in `css/style.css`.
  A preload only counts if its resolved URL matches the request the CSS makes.
- The three `media` ranges overlap by one pixel on purpose. Viewport width is
  fractional under browser zoom and fractional OS scaling, so abutting ranges leave
  gaps a real width can land in, and a gap means no preload fires at all. The overlap
  costs one redundant fetch at exactly 1281px and 1921px.

A browser that fails the `@supports` test still honors the preload, because
`type="image/webp"` gates only on decode support, so it fetches a WebP it will not
paint. That waste is accepted; the alternative is dropping the preload and losing the
LCP win for everyone.

## Development Workflow

### Testing Locally
Since this is a static site with no build process, you can:
1. Open `index.html` directly in a browser, OR
2. Run a simple HTTP server:
   ```bash
   python3 -m http.server 8000
   # Visit http://localhost:8000
   ```

Note that `python3 -m http.server` sends no compression, while GitHub Pages serves
brotli and gzip. Do not benchmark performance against it: the same build scored 81
on Lighthouse mobile uncompressed and 95 with compression enabled. Measure against a
compressing server if the number matters.

### Verifying the asset budget

```bash
python3 tools/verify_assets.py
```

Exits 0 when the issue #15 acceptance criteria still hold: no dead library ships, no
oversized original returns, every optimized variant the site references is present,
every `<img>` carries explicit `width`/`height`, the hero stays under 300 KB, and the
homepage stays under 1 MB. Standard library only. Run it after touching any asset,
markup `<img>` tag, or `<script>`/`<link>` tag.

The dead-asset sweep and the `<img>` dimension scan discover pages with a glob over `*.html` at
the repo root, like `verify_security.py` and `verify_content.py`. They used to name `index.html`
and `resume.html` by hand, which left `thanks.html` exempt from both the moment it was added. A
page with no `<img>` prints a skip line rather than passing silently.

Both scans strip HTML comments first, the way `verify_content.py` always has. A comment has to
quote the thing it explains, and a bare substring scan counts that explanation as the offense it
documents: a comment in `index.html` saying why the Bluesky links carry no `aria-label` contains
the text of an `img` tag, and this file reported it as a real image with no `width`/`height`.
`img/og-card.jpg` is in `SHIPPED_VARIANTS` but deliberately not in `HOMEPAGE_ASSETS`: no page
fetches it, only link unfurlers do, so it is not part of the first-paint budget.

### Verifying the security criteria

```bash
python3 tools/verify_security.py
```

Exits 0 when the issue #17 acceptance criteria still hold: jQuery is at or above 3.5, the
version in the file matches the one named in this document, no GitHub API field is interpolated
into a template literal or an `href`, repo-supplied URLs pass `safeUrl()` before reaching an
`href`, `window.open`, or `setAttribute`, no page or stylesheet requests an `http://` asset, no
IE conditional shim survives, and Font Awesome is one local major site-wide. Standard library
only. Run it after touching the portfolio renderer, any `<script>`/`<link>` tag, or a bundled
library.

The pages it scans are discovered with a glob over `*.html` at the repo root, not a hardcoded
list, so a new page is covered the moment it is added rather than being silently exempt. Two
consequences worth knowing: a missing file is reported as a FAIL and the remaining checks still
run, rather than dying on a traceback partway through; and `privacy.html` is swept even though
it is a vendor-generated Termly document nobody hand-authored, so a regenerated paste containing
an `http://` link would fail the gate with no exclusion mechanism.

It also runs `node --check` over every inline `<script>` on those pages, the way
`verify_interactivity.py` does for `js/main.js`. That loop named `index.html` and `resume.html`
by hand until issue #18; it now sweeps the same globbed page set as everything else, so a new
page is not exempt. Those two are still asserted to carry an inline script, since finding none
there means the extraction pattern broke rather than that the script is gone; a page that
legitimately has none, `thanks.html` or the Termly privacy paste, prints a skip line instead.
Any script tag without a `src` is gated, including `type="module"` and `defer`; only external
`src` tags are skipped. The gated inline
`<script>` in `index.html` runs 466 lines total; about 301 of those are an embedded
CSS-as-a-string block injected via `insertAdjacentHTML`, leaving roughly 165 lines of actual
portfolio-renderer JavaScript, and before this it had no syntax gate at all. `node` is a
convenience, skipped when absent, never a project dependency.

A script tag whose `type` is `application/json` or `application/ld+json` holds data, not
JavaScript, and goes to `json.loads` instead of to `node`. This is not a courtesy: `node --check`
reads the first colon of a JSON-LD block as `SyntaxError: Unexpected token ':'`, so routing it to
node made structured data impossible to ship at all. It is still gated, just by the parser that
matches what it holds, because a malformed JSON-LD block is invisible to a search engine exactly
as a syntax error in the renderer is invisible to a browser. A data block does not satisfy the
"has an inline script to check" assertion on `index.html` and `resume.html`; only real script
does.

Do not mistake the interpolation checks for a general XSS gate. They catch a template literal
written literally at an `innerHTML`/`outerHTML` assignment or an `insertAdjacentHTML` call, and
that is all. Assigning the literal to a variable first, string concatenation, `innerHTML +=`,
`document.write`, `createContextualFragment`, and jQuery's `.html()` and `.append()` all walk
straight past it, and jQuery is loaded on `index.html`. The actual defense is that the renderer
builds DOM nodes and sets `textContent`; the checks only stop that defense from being quietly
undone. They are also blunt in the other direction: any interpolation at those sites fails,
including a safe `${escapeHtml(x)}`, so introducing an escaping helper means changing the rule
first.

### Verifying the content criteria

```bash
python3 tools/verify_content.py
```

Exits 0 when the issue #18 acceptance criteria still hold: the contact form carries a `_next`
that is https, on the host `CNAME` names, and pointing at a page that exists, plus a `_subject`;
`thanks.html` is a complete document with a doctype, charset, viewport, title, and a link back;
no dead form-validation markup or CSS has returned and the spacing that replaced it is still
declared; every `<li>` on every page is closed; the leftover template files stay deleted and
unreferenced; and `resume.html` declares no font family it does not load. Standard library only.
Run it after touching the contact form, `thanks.html`, the contact CSS, or a font stack.

Two things about it that are easy to trip over:

- It strips comments before scanning for dead markup and dead selectors. The checks assert a
  selector is no longer styled and an element is no longer in the markup, and the comment
  explaining why something was removed has to name it. A bare substring scan counted that
  explanation as the offense it documents.
- Like `verify_security.py`, it globs `*.html` at the repo root, so a new page is swept the
  moment it exists.

**Two of issue #18's acceptance criteria were declined by the site owner and are deliberately not
implemented or checked.** `resume.html` is not linked from the nav: the resume is sent on request
rather than published. `privacy.html` is not linked from the footer: that policy belongs to a
different project and is hosted here only so its existing URL keeps resolving. Both pages stay in
the tree, reachable by URL and linked from nowhere. Do not "fix" either as an oversight. Being
unlinked exempts them from nothing, since both verifiers discover pages by glob.

Issue #19 carried that decision through to search engines. Unlinked stops a visitor finding a
page and does nothing to stop a crawler, so both pages now carry a `noindex` as well. See the
next section.

### Verifying the SEO and accessibility criteria

```bash
python3 tools/verify_seo_a11y.py
```

Exits 0 when the issue #19 acceptance criteria still hold: every page is a complete document with
a unique title, a unique description, a self-referencing canonical on the host `CNAME` names, and
an explicit indexing policy; the share card exists at 1200x630 under 200 KB and `index.html`
points at it with absolute Open Graph URLs; the homepage carries `Person` structured data whose
every `sameAs` profile the page also links; every image has alt text that is not its own filename;
every link and button has an accessible name and every decorative icon is `aria-hidden`; every
`target="_blank"` states a `rel`; every contact control has a label and the five FormSubmit field
names are intact; the skip link is the first focusable element and the focus ring is visible; and
card text and focus rings clear their WCAG thresholds. Standard library only. Run it after
touching any page's `<head>`, a link or icon, the contact form, the focus or skip-link CSS, or a
card color.

Things about it worth knowing before editing:

- **`INDEXABLE` and `NOINDEX` must together name every page.** A page in neither fails, on
  purpose: adding a page forces someone to decide whether search engines may list it instead of
  defaulting to indexed. Today only `index.html` is indexable.
- **`robots.txt` must not `Disallow` a noindex page,** and the verifier asserts it does not. A
  Disallow defeats the page's own `noindex`: the crawler is refused the file, never reads the tag
  telling it not to list the file, and can still list the URL from an inbound link alone.
- **Contrast is computed, not asserted.** Both checks read the colors out of the file and
  calculate the ratio, so changing a color rechecks it rather than replaying a stored number.
  Text is held to 4.5:1 and focus rings to the 3:1 that WCAG 2.2 SC 1.4.11 puts on non-text.
- **The focus ring check knows which surface each ring lands on.** This is not hypothetical: the
  first draft painted the ring white over the footer and the nav on the strength of a comment
  calling the footer dark. `.footer` is `#f1f1f1` and `.nav-sticky` repaints the nav `#fff` past
  100px of scroll, so both rings were invisible at about 1.1:1.
- Like the other three, it globs `*.html` at the repo root, and it strips HTML comments before
  every regex scan for the reason `verify_assets.py` now does.

Source-level only, and it says so. That a crawler renders the card, and that a screen reader
announces the names, has to be driven in a browser. Lighthouse is the runtime half:

```bash
python3 -m http.server 8000
npx --yes lighthouse@12 http://127.0.0.1:8000/ --only-categories=accessibility,seo \
  --chrome-flags="--headless"
```

`index.html` scores 100 for accessibility, SEO, and best practices as of issue #19, with no
failing audits. Two notes if you run it on the other pages: `is-crawlable` fails on every page
except `index.html`, which is correct rather than a defect, because those pages carry the
`noindex` the owner asked for and Lighthouse's SEO category penalizes it; and `resume.html` needs
auditing in **both** color schemes, since its dark mode had three AA failures that a light-mode
run never sees.

### Regenerating optimized images

```bash
python3 tools/optimize_images.py /tmp
```

The originals are deliberately not in the working tree, because one was 39 MB. The
script's docstring lists the `git show 3b42a25:img/...` commands that recover them.
Requires Pillow. Never commit a full-resolution camera original.

### Regenerating the share card

```bash
python3 tools/make_og_card.py
```

Rebuilds `img/og-card.jpg` from `img/hero-1280.jpg`: a cover-crop to the 1.91:1 every unfurler
expects, under the same `rgba(0, 0, 0, 0.4)` scrim `.home-1:after` paints over the hero, with the
hero's own two lines of copy over it. A shared link then previews as the top of the site instead
of drifting away from it. Requires Pillow, run by hand, never part of the gate.

It is a JPEG even though issue #19 asked for a PNG. The card is a photograph: lossless PNG at
1200x630 lands near a megabyte, five times the 200 KB budget the same issue sets, and quantizing
to fit bands the sky and the water. Every unfurler accepts JPEG. It ships at 174.7 KB, and
`verify_seo_a11y.py` asserts the dimensions and the budget, so any replacement has to hold both.
The page sets Lato, which is fetched from Google Fonts and is not on disk, so the script falls
back through Open Sans, Liberation Sans, and DejaVu Sans; the card is generated once and
committed, so that chain only has to resolve on whichever machine regenerates it.

### Making Changes

**HTML Files**: Edit directly - no build step needed

**CSS Changes**:
- Main styles: `css/style.css`
- Some critical CSS is embedded in `index.html` (portfolio section styles)

**JavaScript Changes**:
- Main logic: `js/main.js`
- Some inline JavaScript in `index.html` (portfolio loading logic in the `<script>` block before `</body>`)

**Important**: When modifying the portfolio loading logic in index.html, the JavaScript and CSS are both inline. The portfolio cards system includes both functionality and styles in the same section.

### GitHub API Rate Limiting
The portfolio section fetches from GitHub API. Be aware:
- Unauthenticated requests have 60 requests/hour limit
- Error handling is implemented (the `catch` in `loadPortfolio()` in index.html)
- Consider this when testing portfolio loading features

## Common Tasks

### Updating Portfolio Content
Portfolio items are automatically pulled from GitHub repos with "portfolio" in the description. To add/modify:
1. Update the repo's description on GitHub to include "portfolio"
2. Site will automatically show it on next load

### Updating Resume
Edit `resume.html` - it's a standalone HTML file with inline styles and JavaScript.

### Modifying Contact Form
The form submits to FormSubmit (the `<form id="contact-form">` action in index.html). To change:
- Update the action URL with new FormSubmit endpoint
- Honeypot field is present for spam protection (the hidden `_honey` input)
- `_next` and `thanks.html` move together. Renaming or deleting the page without updating the
  hidden field sends every visitor who submits the form to a 404, which is why
  `verify_content.py` resolves the `_next` path against the repo
- `_next` is absolute and must stay on the host `CNAME` names. Changing the custom domain means
  changing this value too, and the verifier fails until both agree

### Adding/Changing Images
Every raster image ships at roughly 2x its largest CSS display size, as WebP with a
fallback, and every `<img>` carries explicit `width`/`height` to prevent layout shift.

- Hero background: `img/hero-{1280,1920,2560}.webp` plus `img/hero-1280.jpg`, wired in the `.home-1` rule and the `@supports` block after it in `css/style.css`
- Profile avatar: `img/portrait-340.{webp,jpg}` in the `<picture>` inside `.avatar-hero` in `index.html`
- Badges: `img/cesium-120.{webp,png}` and `img/qr_code-240.png` in `.badge-container` in `resume.html`
- Social icons: `img/Bluesky.svg`
- Share card: `img/og-card.jpg`, named by the `og:image` in `index.html` and rebuilt by
  `tools/make_og_card.py`. The only image here no page fetches; it exists for link unfurlers.

Every `<img>` also needs alt text that is not its own filename. An empty `alt` is correct for a
decorative image and a missing one never is.

The QR is 240x239, not square, because its source is 1680x1670. Preserve that aspect
ratio when regenerating, and keep the `height` attribute matching whatever the script
actually emits.

`resume.html` sets `.badge-container img { display: block }` deliberately. Without it
the badge inside the `<picture>` gains baseline descender space and measures 64px
against the bare image's 60px. Setting `display` on the `picture` element instead has
no effect.

## Deployment

The site is deployed via GitHub Pages:
1. Push changes to the `main` branch
2. GitHub Pages automatically deploys from the root directory
3. Custom domain configured via `CNAME` file (www.geobrad.dev)

No build or deployment scripts needed - changes go live automatically after push.

## Important Notes

- **No Build System**: This is intentional - keep it simple with no npm/webpack/bundling. `tools/` holds standalone scripts run by hand, not a build step. The `npx lighthouse` line in the SEO section is a measurement run by hand for the same reason, not a dependency.
- **Five verifiers, all standard library, all run by hand**: `verify_assets.py`, `verify_security.py`, `verify_content.py`, `verify_interactivity.py`, `verify_seo_a11y.py`. Each one pins the acceptance criteria of the issue that created it, so together they are the regression suite this repo has instead of tests. Run all five before opening a PR.
- **jQuery Dependency**: The entire site relies on jQuery. Modern JavaScript refactoring would require significant rewrite
- **Bootstrap 3**: Using older Bootstrap version. Upgrading requires CSS/HTML updates
- **Responsive Design**: Mobile-responsive via Bootstrap grid and custom media queries
- **Browser Support**: Targets modern browsers with fallbacks for animations
- **Dead CSS remains**: `css/style.css` still holds rules for the removed libraries (`#particles-js`, `.owl-*`, `.mfp-*`, `.home-carousel`, `.testimonial-slider`). Unmatched selectors are harmless. This was previously described here as "tracked separately in issue #18", which was wrong: issue #18 turned out to be the content and navigation issue and did not touch them. No open issue covers this cleanup, so file one before assuming someone else will.
