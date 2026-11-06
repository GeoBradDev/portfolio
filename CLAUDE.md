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

- **Frontend**: Vanilla HTML5, CSS3, JavaScript. No framework and no third-party runtime library.
- **Layout**: CSS grid and flex rules in `css/style.css`. The only external stylesheet is Google
  Fonts (Lato), which is a font, not a library.
- **Icons**: inline SVG, from a hidden `<symbol>` sprite on each page that uses them
- **Deployment**: GitHub Pages with custom domain (CNAME)

Owl Carousel, Magnific Popup, Isotope, imagesLoaded, jQuery Typer, and Particles.js
were removed in issue #15. None of them had a matching element on any page, so all
of them downloaded and did nothing. Do not reintroduce a library without an element
that actually uses it.

jQuery 3.7.1, Bootstrap 3.4.1, and Font Awesome 4.7.0 were removed in issue #31. Bootstrap 3 and
Font Awesome 4 are end of life, and jQuery was pinned to its maintenance-only 3.x line by
Bootstrap, which cannot run on jQuery 4. The site used all three for very little: Bootstrap's
JavaScript drove one collapse, jQuery drove `js/main.js`, and about twenty glyphs came from Font
Awesome. Their files and the `fonts/` directory are gone, and `tools/verify_assets.py` lists them
as dead assets so that a copy coming back fails the gate. In `tools/verify_security.py`,
`check_no_end_of_life_library` holds every `<script src>` and script or module preload to `js/`,
every stylesheet and style preload to `css/` or Google Fonts, and every other preload or
prefetch to the site or Google Fonts, and rejects `<base>`, off-site
imports in scripts, and a vendored library's banner in any first-party script or stylesheet a
page loads; `check_css_imports_are_first_party` rejects a third-party `@import` or `url()`. Adding a library means
changing that check first, deliberately.

Icons are Font Awesome 4.7's own outlines, extracted once from the deleted SVG font into a
`<svg aria-hidden="true" focusable="false" style="display:none">` sprite of `<symbol id="icon-NAME">` elements,
one sprite per page (`index.html` and `resume.html`), with an SIL OFL 1.1 attribution comment
above each. An icon is `<svg class="icon icon-NAME" aria-hidden="true" focusable="false"><use
href="#icon-NAME"></use></svg>`; the portfolio renderer builds the same with `icon(name)` via
`createElementNS`. `privacy.html`, `thanks.html`, and `404.html` have no sprite, so an icon added
to one of them needs its symbol added with it. Rules the verifiers hold:

- Every `<svg>`, static or built by the renderer, carries `aria-hidden="true"` and
  `focusable="false"` (`verify_seo_a11y.py`). Every icon-only control keeps its `aria-label`.
- Every `<use href="#icon-X">` and every `icon("X")` resolves to a `<symbol id="icon-X">` on the
  same page, and `icon()` takes only a string literal so the name can be checked
  (`verify_security.check_icons_are_inline_svg`). A missing symbol renders an empty box with no
  error anywhere else.
- No `fa`, `fa-*`, `fas`, `fab`, `far`, or `fal` class anywhere, and no Bootstrap grid or utility
  class (`col-*`, `row`, `pull-*`, `btn`, `hidden-*`, `clearfix`, and the rest of `BOOTSTRAP_CLASS` in
  `verify_seo_a11y.py`). A class `index.html` keeps with a local rule (`LOCAL_CLASSES`:
  `container`, `sr-only`, `text-center`, `nav`, `icon-bar`, the `navbar-*` names) must have a
  rule that styles it at rest in `css/style.css`.
- An icon's width comes from a per-icon `.icon-NAME` rule, because an inline SVG with no width
  attribute is 300px wide. `resume.html` sizes its icons with `.glyph`, since `.icon` there
  already means the blue color and the 8px margin, and the PDF button's icon has to stay white.

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
  carries its own copy of `thanks.html`'s four style rules rather than pulling in
  `css/style.css` for one panel. Its favicon `href` is root-absolute, unlike every other page's: Pages serves this
  document at the URL that was requested, without redirecting, so a relative href resolves
  against the mistyped path.
- `robots.txt` - Allows everything and names the sitemap. Deliberately Disallows nothing; see
  the SEO section below for why.
- `sitemap.xml` - One entry, the homepage. The other four pages are noindex.
- `projects.json` - The portfolio cards, generated by `tools/build_projects.py` and
  committed. Fetched by `index.html` on every load. Generated, so do not hand-edit it;
  change the repo on GitHub and re-run the script.
- `css/style.css` - Every stylesheet rule the site has, including the portfolio cards
- `js/main.js` - Navigation, scroll, and skill-bar logic. Loaded by `index.html` only.
- `img/` - Images including profile photo, badges (Cesium certification, QR code), and
  `og-card.jpg`, the 1200x630 link-unfurl card
- `tools/` - Standalone dev-time Python scripts. The deployed site never runs them.

## Key Features & Architecture

### js/main.js

Loaded by `index.html` only; `resume.html` and `privacy.html` are standalone. Vanilla
JavaScript, no library, since issue #31. It drives the sticky navbar,
active-link tracking, the mobile menu toggle, the scroll-to-top button's visibility, the
skill bars, and making the section an in-page link targets focusable for that click. It
does not scroll the page or move focus into a section: both are the browser's native
fragment navigation (see Navigation & Scrolling).

Everything in it has a matching element in `index.html`. That is the rule the file
exists to keep: it once held 664 lines, roughly 500 of which targeted elements no
page contained, and the whole file went unloaded for two years without anyone
noticing (issue #16). Do not add a block here without an element that uses it, and
run `python3 tools/verify_interactivity.py` after touching `js/main.js` or the
markup it depends on.

Invariants that are easy to break by accident:

- Skill bar widths come from `data-percent` on `.progress-bar-line`, never from an
  inline `style`. CSS starts the bars at 5% and JavaScript animates them to the
  target once the section scrolls into view. With JavaScript off the bars stay at
  5%; that is accepted, since the portfolio section already requires JavaScript.
- `navHeight()` subtracts the open menu while the toggle is shown. Below 768px the
  expanded menu is in flow inside the fixed header, so measuring it raw returns 278px
  against the 63px it collapses back to. It now feeds only the active-link probe; the
  scroll landing comes from CSS (below), and it works because the menu's link click
  handler closes the menu before the browser performs the fragment navigation.
- The mobile toggle is a plain `<button type="button" aria-expanded aria-controls="bm-navbar">`,
  and `aria-expanded` is the single source of truth: `#bm-navbar` shows from `.is-open`, and
  `.is-collapsing` exists only during the 350ms height animation, skipped under reduced
  motion. The hidden state is a base rule and only `@media (min-width: 768px)` overrides it.
  It used to sit in a `max-width: 767px` query, which left fractional widths between the two
  breakpoints (browser zoom) with the menu showing and a toggle that did nothing;
  `verify_interactivity.check_collapse_covers_every_width` and `check_nav_breakpoints` hold
  that. A second tap during the animation reverses it, where Bootstrap ignored it; that is
  deliberate.
- `html.smooth-scroll` is added a frame after `load`, not at first paint. With
  `scroll-behavior: smooth` on bare `html`, a deep link's initial jump animates against a
  layout that is still settling and lands short. `check_deep_link_is_not_animated` and
  `check_smooth_scroll_starts_on_load` hold it.
- Nothing covers the page by default and waits for script to uncover it. `index.html`
  opened with a fixed, full-viewport `.loader-con` that only this file and the portfolio
  renderer ever hid, so with JavaScript off the homepage was a blank panel forever, and with
  it on, parsed content sat under the panel after first paint. Issue #32 deleted it outright:
  the page is static and its hero image is preloaded, so a loader only delays content. A
  full-screen element that script opens later, a modal or a menu, must be hidden in its own
  base rule (`display: none`, `visibility: hidden`, or `opacity: 0` with
  `pointer-events: none`) and shown by a class. `check_no_script_removed_overlay` holds this
  on every page; its docstring lists the CSS forms it cannot read.

The hero has no parallax. `.home-1` uses `background-size: cover`, so shifting
`backgroundPosition` slides the image down and exposes blank space under the
overlay. The `parallax()` function and the `parallax` class were removed together.

`.portfolio-overlay` must keep `pointer-events: none`. It covers the whole card at
`z-index: 3` above the content at `z-index: 2`, and an `opacity: 0` element is
still hit-testable, so without it the overlay swallows every click and the "Live
Demo" and "Code" anchors become unreachable. The rule lives in `css/style.css` since
issue #20, and `verify_interactivity.check_card_handler` reads it from there while
reading the click handler it pairs with from `index.html`, which is why that one check
takes both files.

### Portfolio Loading

The portfolio section renders from `projects.json`, a committed file generated by
`tools/build_projects.py`. **The page makes no GitHub API call.** Issue 20 replaced three
per-page-load calls to `api.github.com`, one per account, with one same-origin static
fetch. The unauthenticated limit is 60 requests per hour *per IP address*, so roughly 20
loads from behind one NAT used to blank the section for everyone sharing that address.
`verify_portfolio.py` asserts the hostname does not appear in `index.html`.

- The inline `<script>` before `</body>` fetches `/projects.json`, root-absolute to match
  the image URLs in `css/style.css` and the preloads in the head. The file's order is the
  display order; the renderer re-sorts nothing.
- Cards are built with `document.createElement` and `textContent`, never a template
  literal, so a hostile repo `name` or `description` can only ever render as text
- `safeUrl()` gates the "Live Demo" and "Code" links: it accepts only an `https:` URL and
  returns `null` otherwise, and a `null` result means that link, or the whole-card click
  handler, does not render at all. It runs even though the generator already validated,
  because a hand-edited `projects.json` is still untrusted input
- The card CSS lives in `css/style.css`, at the end of the file. It was ~300 lines built
  as a string in JavaScript and injected with `insertAdjacentHTML` on every page load,
  which delayed styling until the script ran and kept the browser from caching it
  separately. Do not move it back; `verify_portfolio.py` rejects both `portfolioCSS` and
  `insertAdjacentHTML` in `index.html`.

**Comments in that inline `<script>` must not contain the literal strings
`api.github.com`, `portfolioCSS`, or `insertAdjacentHTML`.** `verify_portfolio.py` strips
HTML and CSS comments before scanning but deliberately not JavaScript `//` comments: a
`//` regex cannot tell a comment from the `//` in `https://`, and deleting real code from
the scanned text would turn a FAIL into a silent PASS. The comment explaining why the
renderer no longer calls the API says "the GitHub API" rather than the hostname for
exactly this reason.

#### tools/build_projects.py

```bash
python3 tools/build_projects.py
```

Standard library only, run by hand like `optimize_images.py` and `make_og_card.py`. No
scheduled job runs the script; the site owner chose that on 2026-08-13 over a scheduled
GitHub Action, so **the data is only as fresh as the last run**. Re-run the script after
adding the topic to a repo, editing a description, or redeploying a demo that had gone
dark. The `verify` workflow added in issue #35 checks `projects.json` but never
regenerates it and never calls the API. The `generated` timestamp in `projects.json` is there so a reader can see how stale it is.

- **Filters on the `portfolio` GitHub topic, not on the description.** The old filter
  looked for the word in the description, which put a control flag in copy that visitors
  to the repo read and broke silently whenever a description got reworded. Tagging a repo
  with the topic is now the only way to add it to the site.
- **Skips archived repos.** An archived repo is frozen: its demo is usually gone and its
  description cannot be edited. This is what drops the two CleanUpCoop forks.
- **Probes every `homepage` and omits the ones that do not answer.** Four of the six demo
  links were 404ing outright on 2026-08-13. A card whose demo is dead renders with a Code
  link alone, which is the point: a Live Demo link to nothing is worse than no link.
- **Sorts by `pushed_at`, never `updated_at`.** `updated_at` bumps on any metadata change,
  so editing seven descriptions flattens seven repos to the same minute and destroys the
  order. That is not hypothetical; it happened while working issue 20.
- **One failing account costs only its own repos.** Every account failing raises instead,
  because writing an empty `projects.json` would blank the section more thoroughly than
  the bug this guards against.
- `GITHUB_TOKEN` or `GH_TOKEN` raises this script's own rate limit and is optional.
  **The token goes only to `api.github.com`.** `probe()` builds a bare request with a
  User-Agent and nothing else, because a `homepage` is whatever a repo owner typed, it can
  redirect anywhere, and `urllib` copies every header except content-length and
  content-type onto a redirect target. Use `github_request()` for the API and never for a
  probe. Dropping `Accept: application/vnd.github+json` from the probe matters too: a host
  doing strict content negotiation answers it with a 406, which would read as dead and
  silently drop a live demo.

`ACCOUNTS` holds `GeoBradDev` and `Seaside-Sustainability-Web-GIS`. `MapTheVoteSTL` was
removed (issue 20, criterion 4): its one repo has no description and no topic, so it could
never contribute a card. Seaside stays despite contributing nothing today, because with no
visitor-side API call an account that matches nothing costs nothing, and a future repo
there then appears without a code change.

### Navigation & Scrolling

Function names, not line numbers, because line numbers go stale.

- `stickyNav()` adds `.nav-sticky` past 100px and reveals `.scroll-up` past 1000px
- Nav links, the hero chevron, and `.scroll-up` (`href="#"`) are plain fragment links. No
  JavaScript cancels their click or scrolls the page, so the browser updates `location.hash`
  and Back returns to the previous section. `css/style.css` sets `scroll-behavior: smooth` on
  `html.smooth-scroll` inside `@media (prefers-reduced-motion: no-preference)`, so a visitor
  who asked for reduced motion gets a jump, and `.one-page-section { scroll-margin-top: 63px }`
  lands each section below the collapsed sticky header, which measured 63px at both 375px and 1440px. Change
  that value if the sticky header's height changes; the verifier only asserts it is positive.
  The per-link `data-speed` durations of the old jQuery animation are gone.
- **An in-page link moves focus into its target, but only for the click that activates it**
  (issue #33). A plain section is not focusable, so native fragment navigation scrolled to it
  and left focus on `<body>`, and nothing told assistive technology the reading position
  moved. The document click listener in `js/main.js` sets `tabindex="-1"` on the target for
  that one click, without cancelling it, so the browser's own fragment focusing moves focus
  there. It removes the attribute on blur, and a `window` `hashchange` listener blurs a section
  that history traversal leaves focused, so Back then Tab behaves as on `main`.
  `.one-page-section:focus { outline: none }` hides the ring on the focused section only: it is
  a reading position, not a control, and every control keeps its `:focus-visible` ring.
- **In `index.html`, never put a static `tabindex` on a section, or a `tabindex` of 0 or more on
  anything.** A static one on the sections was the first fix tried for issue #33, and it
  regressed mouse and touch users: a click or tap on plain content inside a section then
  focuses the whole section, and the next Tab restarts at its first control instead of after
  the clicked spot, scrolling the page backwards. A `tabindex` of 0 adds a non-control to the
  tab order, and a positive one reorders it. Every fragment link in `index.html` that names an
  id (all but back to top's bare `#`) must also target a `.one-page-section`, so the outline
  rule covers whatever takes focus this way. `verify_interactivity.check_link_targets_take_focus`
  holds these rules at the source level for every section a link targets, but its handler
  checks only assert the pieces are present, so after touching the listener, drive the
  behavior in a browser and compare it with `main`. One limit is accepted: after a link
  focuses a section, a mouse click on non-control content inside that still-focused section
  followed by Tab restarts from the section top.
- The `scroll` class on the nav links and the hero chevron drives nothing in CSS or JavaScript.
  `verify_interactivity.py` uses it to find the nav targets, so keep it.
- `changeActiveNavLink()` highlights the link for the visible `.one-page-section`, probing at
  `scrollY + navHeight() + 1` against each section's border box (`offsetHeight`). A section
  without that class never highlights, which is how `#portfolio` was silently excluded before
  issue #16. jQuery's `.height()` measured the content box, which left each section's bottom
  padding as a band where the previous link stayed lit.
- All three run from one passive `scroll` listener and a `resize` listener, throttled to one
  pass per frame with `requestAnimationFrame`, and once on ready so a deep link or a reload
  partway down the page starts in the right state

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
  weightless: each was `display: block` with `margin-top: 8px` plus `.mb-30`, inside the floated
  Bootstrap columns of the time, where those margins could not collapse away, and removing them
  alone collapsed the form from 387px to 289px. `.input-field`'s `margin-bottom` and
  `textarea.input-field`'s `margin-bottom` carry that spacing. Since issue #31 the form is a CSS
  grid (`#contact-form { display: grid; column-gap: 30px }`, two columns from 768px, one
  `.form-field` wrapper per field, the button spanning both columns as the last row), and each
  grid item contains its field's margins exactly as the floated column did. The textarea's 68px
  measures 76px on screen because the textarea is inline-level and the line box adds its
  descent. `verify_content.py` asserts the two margins and the grid declaration. The form
  measures 387.5px at 1440 and 461.75px at 375, unchanged by the move off floats.
- Each field carries a `.sr-only` `<label for>` added in issue #19. The placeholders stay, but a
  placeholder is a hint rather than a name: it disappears the moment the field has content, which
  is exactly when someone tabbing back through a half-filled form needs to know what it holds.
  `.sr-only` is the site's own rule in `css/style.css` (the standard clip pattern, the same
  declarations Bootstrap 3 shipped) and takes the label out of flow, so the form still measures
  387.5px. `verify_seo_a11y.check_no_bootstrap_classes` fails if that rule disappears, because an
  unstyled `.sr-only` label renders visible and grows the form.
  `verify_seo_a11y.py` asserts every visible control is labelled and that the five FormSubmit
  field names are unchanged; the honeypot is exempt by shape, since labelling it would advertise
  it to the bots it exists to catch.

### Accessibility

The invariants issue #19 established. `tools/verify_seo_a11y.py` holds all of them.

- **The skip link is the first focusable element in `index.html`,** and targets `#about` rather
  than `#home` because the hero holds nothing to read. It is parked at `top: -100px` and pinned to
  `top: 12px` on focus, at `z-index: 200` so it clears `.nav-wrapper` at 20. It styles `:focus`,
  not `:focus-visible`: the link is invisible until focused, so there is no mouse-click case to
  suppress.
- **`css/style.css` must never suppress the focus outline unconditionally again.** It set
  `outline: none` on `a, a:focus, a:hover, a:active` plus `.input-field` and `.submit-btn`, which
  left every keyboard user navigating blind. `:focus-visible` now carries the ring. The one
  exception is a focused `.one-page-section`, a reading position rather than a control; see
  Navigation & Scrolling.
- **No rule may paint a ring on plain `:focus`.** Until issue #31, `bootstrap.min.css` carried
  `a:focus { outline: 5px auto -webkit-focus-ring-color }`, and an
  `a:focus:not(:focus-visible) { outline: none }` rule in `style.css` held it back. With Bootstrap
  gone that rule had nothing left to suppress, since the browser's own stylesheet keys its ring on
  `:focus-visible`, so it was deleted. What it protected is now asserted directly:
  `check_skip_link_and_focus_visibility` fails if any stylesheet a page links sets a visible
  `outline` or `box-shadow` in a rule whose selector has `:focus` without `:focus-visible`
  (`.skip-link:focus` is exempt). A mouse click paints no ring; Tab paints the 2px ring.
- **A focus ring's color has to suit the surface under it.** White over the hero and the
  transparent nav; `#232323` everywhere else, including the footer at `#f1f1f1` and the nav once
  `.nav-sticky` repaints it `#fff` past 100px of scroll. This covers the mobile nav toggle, which
  has shown the keyboard ring since issue #31; Bootstrap's `.navbar-toggle:focus { outline: 0 }`
  had hidden it.
- **Every icon-only control has an `aria-label` and every `<svg>` icon has `aria-hidden="true"`
  and `focusable="false"`.** The
  two Bluesky links get neither: their `<img alt="Bluesky">` already names them, and a label would
  win over the alt and leave it dead.
- **Hero text is measured against a white photo pixel under the scrim.** The photo cannot be
  read from source and no automated audit measures text over an image, so
  `check_hero_text_contrast` takes the brightest pixel any photo can hold, composites the
  `.home-1:after` scrim over it (and, for the photo credit, the credit's own black backing), and
  holds the subtitle to the 3:1 large-text bar and the credit and its link to 4.5:1. That worst
  case is real, not theoretical: the subtitle crosses sun glints on the water that are
  effectively pure white. Lightening the scrim, dimming the subtitle, or dropping the credit's
  backing fails the gate. Only flat black `rgba()` layers can be bounded this way; a gradient or
  image scrim fails the parse and forces the check to be rewritten with it. The credit link is
  underlined because it shares the credit's color, so the underline is what tells it apart
  (SC 1.4.1).
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
  file they cannot decode and paint no hero at all, only the scrim from
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
Since this is a static site with no build process, run a simple HTTP server:

```bash
python3 -m http.server 8000
# Visit http://localhost:8000
```

**Opening `index.html` from the filesystem no longer renders the portfolio section.** It
used to, because `api.github.com` sends `Access-Control-Allow-Origin: *` and answers a
request from a `file://` origin. Since issue 20 the renderer fetches `/projects.json`
instead, and under `file://` that resolves to the filesystem root and fails, so the
section shows its error state. Everything else on the page still works. Use the server.

Note that `python3 -m http.server` sends no compression, while GitHub Pages serves
brotli and gzip. Do not benchmark performance against it: the same build scored 81
on Lighthouse mobile uncompressed and 95 with compression enabled. Measure against a
compressing server if the number matters.

### Continuous integration

`.github/workflows/verify.yml` runs the six verifiers on every pull request and on every push
to `main` (issue #35). It sets up Python and node, then runs each `python3 tools/verify_*.py`
as its own step under `if: ${{ !cancelled() }}`, so one run reports all six and the job fails
if any one does. It needs no secrets, holds only `contents: read`, checks out with
`persist-credentials: false`, and makes no network call beyond checkout and toolchain setup;
`--check-links` stays out of it for the reason given under "Verifying the portfolio data
criteria".

- **The check is named `verify`, after the job id, and that name must not change.** Branch
  protection on `main` requires it, requires changes to arrive by pull request, and does not
  enforce either rule on admins, so an admin can still push to `main` directly or merge a PR
  whose `verify` failed. Renaming the job, giving it a `name:`, or adding a matrix changes the
  reported name, and the required check then never reports. Branch protection lives in the
  repo settings, not in a file here, so nothing in the tree would notice it being changed.
- **Pages does not wait for the gate.** It still deploys with the `legacy` build from `main`, so
  an admin push straight to `main` publishes whether or not `verify` passes. The gate protects
  merges, not deploys.
- **A new verifier must be added to the workflow in the same change.**
  `verify_security.check_ci_workflow` compares the `tools/verify_*.py` files on disk with the
  steps the `verify` job runs and fails on any difference. It also rejects the ordinary edits
  that would let the job pass without gating: a verifier step that cannot fail, a skipped job or
  setup step, a `paths`, `types`, `tags`, or `branches-ignore` style filter, a `branches:` list
  without `main`, a write permission, a secret, an unlisted action, or a network command. It
  guards against accidental drift, not against every possible extra step: one that tampers
  with the verifiers before they run without naming them would get past it. It reads the file
  with line regexes, so it expects plain block-style YAML with two-space indents and fails on
  other styles rather than guessing at them. If it rejects a harmless edit, rewrite the edit in that
  style rather than loosening the check.
- Run the verifiers locally before pushing anyway. The workflow tells you after the push; the
  local run tells you before it.

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
`projects.json` is the opposite case and joined `HOMEPAGE_ASSETS` in issue #20, because the
renderer fetches it on every load. The homepage has sat well under the 1024 KB budget since
issue #31 removed jQuery, Bootstrap, and Font Awesome. The verifier prints the current figure;
this file does not pin the total, because every asset change on the homepage moves it.

### Verifying the security criteria

```bash
python3 tools/verify_security.py
```

Exits 0 when the issue #17 acceptance criteria still hold: no repo field is interpolated into a
template literal or an `href`, repo-supplied URLs pass `safeUrl()` before reaching an `href`,
`window.open`, or `setAttribute`, no page or stylesheet requests an `http://` asset, and no IE
conditional shim survives. Issue #31 replaced its jQuery version floor and its Font Awesome
check: every page now loads only first-party scripts and stylesheets plus Google Fonts, with no
third-party `@import` or `url()` (see Technology Stack), and every icon is an inline SVG whose
symbol resolves. Since issue #35 it
also checks that `.github/workflows/verify.yml` still runs every verifier and still gates; see
Continuous integration above. Standard library only. Run it after touching the portfolio
renderer, any `<script>`/`<link>` tag, a vendored file, `.github/workflows/verify.yml`, or
the set of `tools/verify_*.py` files.

**`remote_fields` must name fields the renderer actually reads, and the renderer's loop
variable must stay named `repo`.** Three of those checks are pinned to the literal text
`repo.` at a sink, so renaming the variable leaves all three matching nothing and passing
vacuously. Issue #20 renamed the fields when the renderer stopped calling the API directly:
`homepage`, `html_url`, and `stargazers_count` became `demo`, `code`, and `stars`, and the
list was updated with them. A field left in that list after the renderer stops reading it is
an assertion that can no longer fail.

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
`<script>` in `index.html` runs 189 lines, all of it real JavaScript, and before this it had
no syntax gate at all. It used to run 466 lines, of which about 301 were a CSS-as-a-string
block injected via `insertAdjacentHTML`; issue #20 moved that CSS to `css/style.css`. Locally `node`
is a convenience, skipped when absent, never a project dependency. CI is the exception: the
`verify` workflow sets node up and `check_ci_workflow` fails without it, because a silent skip
there would leave the gate checking less than it reports.

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
`document.write`, and `createContextualFragment` all walk straight past it, as would any DOM
library's markup methods if one were ever loaded again. The actual defense is that the renderer
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
names are intact; the skip link is the first focusable element and the focus ring is visible;
card text and focus rings clear their WCAG thresholds; and the hero subtitle and photo credit clear
theirs against a white photo pixel under the scrim, with the credit link underlined and the share
card's scrim matching the hero's. Standard library only. Run it after
touching any page's `<head>`, a link or icon, the contact form, the focus or skip-link CSS, a
card color, or the hero scrim or hero text colors.

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
  Both read `css/style.css`. The hero text check is computed the same way, against a surface
  composited from the declared layers over white rather than a color any one rule states. The card colors used to be read out of `index.html`, where the
  card CSS lived as a string in JavaScript; issue #20 moved the CSS and this with it.
  `.portfolio-error` joined the list then, and declares its own `background` for a reason:
  `#portfolio` paints a gradient, and a ratio can only be computed against a color the rule
  states.
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

`index.html` scores 100 for accessibility and SEO, re-confirmed on 2026-11-05 after issue #31
replaced the libraries, the nav, the form layout, and the icons, with no failing audits; best
practices was last confirmed at 100 on 2026-08-13, after issue #20. `resume.html` scored 100 for
accessibility in both color schemes on the same 2026-11-05 run.
Two notes if you run it on the other pages: `is-crawlable` fails on every page
except `index.html`, which is correct rather than a defect, because those pages carry the
`noindex` the owner asked for and Lighthouse's SEO category penalizes it; and `resume.html` needs
auditing in **both** color schemes, since its dark mode had three AA failures that a light-mode
run never sees.

### Verifying the portfolio data criteria

```bash
python3 tools/verify_portfolio.py
python3 tools/verify_portfolio.py --check-links   # adds a live probe, needs the network
```

Exits 0 when the issue #20 acceptance criteria still hold: `index.html` names no GitHub API
host and reads `projects.json`; that file parses, is non-empty, and every entry has a name, a
string description and language, a non-negative star count, an https `code` URL, a `demo` that
is https or absent, and a `pushed` stamp; the entries are ordered by last push, newest first;
no description carries the `#portfolio` flag; the generator selects on the topic and rejects a
description match, an archived repo, and a repo with no `topics` key; one failing account still
lets the others through while every account failing raises; a demo that does not answer is
dropped and a non-https one is dropped without probing; the card CSS is in `css/style.css` and
neither `portfolioCSS` nor `insertAdjacentHTML` survives in `index.html`; and no pictograph
reaches `index.html` or `projects.json`. Standard library only. Run it after touching the
renderer, the generator, `projects.json`, or the card CSS.

Things about it worth knowing before editing:

- **The four generator checks call the real functions with an injected fetcher and an injected
  probe.** Scanning `build_projects.py` for the word "topics" would pass the moment the word
  appeared anywhere in it. Calling `select_repos` with a repo that has the word in its
  description and no topic is the only way to know what it actually selects.
- **The default run is offline and deterministic, like the other five.** `--check-links` is the
  live half and is deliberately not part of the gate: a check that fails because someone's wifi
  dropped teaches people to ignore the gate. The criterion is still enforced, at generation
  time, by the probe in `build_projects.py`.
- **The emoji scan covers `index.html` and `projects.json`, not every page.** `resume.html`
  carries a moon and a sun glyph on its dark mode toggle. Those are visible UI on a page issue
  20 does not mention, and replacing them is a design change that issue did not ask for. This
  is the one place the repo's glob-every-page convention is deliberately not followed, and the
  docstring says so.
- A pictograph in a repo description would make the generator write a file this rejects.
  `build_projects.py` warns and names the repo and codepoint at generation time, which is where
  the fix is: the description lives on github.com.

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
expects, under the same scrim `.home-1:after` paints over the hero, with the hero's own two lines
of copy over it in the hero's own colors. The script's `SCRIM` must equal the alpha in that rule,
and `verify_seo_a11y.py` fails when they differ, so a scrim change means regenerating the card. A shared link then previews as the top of the site instead
of drifting away from it. Requires Pillow, run by hand, never part of the gate.

It is a JPEG even though issue #19 asked for a PNG. The card is a photograph: lossless PNG at
1200x630 lands near a megabyte, five times the 200 KB budget the same issue sets, and quantizing
to fit bands the sky and the water. Every unfurler accepts JPEG. `verify_seo_a11y.py` asserts the dimensions and the budget, so any replacement has to hold both.
The page sets Lato, which is fetched from Google Fonts and is not on disk, so the script falls
back through Open Sans, Liberation Sans, and DejaVu Sans; the card is generated once and
committed, so that chain only has to resolve on whichever machine regenerates it.

### Making Changes

**HTML Files**: Edit directly - no build step needed

**CSS Changes**:
- All of it: `css/style.css`. `index.html` carries no `<style>` block and no CSS string
  since issue #20; the portfolio card rules are the last section of the stylesheet

**JavaScript Changes**:
- Main logic: `js/main.js`
- Some inline JavaScript in `index.html` (portfolio loading logic in the `<script>` block before `</body>`)

**Important**: The portfolio renderer is inline in `index.html`, but its CSS is not. Issue 20
moved the card styles to `css/style.css`; only the JavaScript is still in the page.

### GitHub API rate limiting

**No longer applies to visitors.** The page reads the committed `projects.json` and never
calls the API, so the 60-requests-per-hour unauthenticated limit cannot affect a page load.
It still applies to `tools/build_projects.py`, which makes one request per account plus one
per repo homepage it probes. That is a handful of calls per run, comfortably inside the
limit; set `GITHUB_TOKEN` if you are iterating on the script.

## Common Tasks

### Updating Portfolio Content

The site shows repos tagged with the **`portfolio` GitHub topic**, not repos with the word
in their description. To add one:

1. Add the `portfolio` topic to the repo on GitHub
2. Run `python3 tools/build_projects.py`
3. Commit the changed `projects.json`

Step 2 is not optional and nothing does it for you. Tagging a repo and stopping there
changes nothing on the site.

A repo will not appear if it is archived, and its "Live Demo" button will not appear if its
homepage does not answer. Both are deliberate; the generator prints a `WARN` naming the
repo in the second case.

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
1. Changes reach `main` by merging a pull request, which must pass `verify` unless an admin
   merges it, or by an admin push
2. GitHub Pages automatically deploys from the root directory
3. Custom domain configured via `CNAME` file (www.geobrad.dev)

No build or deployment scripts needed - changes go live automatically once they land on `main`.
The `verify` workflow does not gate the deploy itself: an admin push to `main`, or an admin
merge of a red PR, publishes without waiting for it. See Continuous integration.

## Important Notes

- **No Build System**: This is intentional - keep it simple with no npm/webpack/bundling. `tools/` holds standalone scripts, run by hand or, for the six verifiers, by the `verify` workflow; none of them is a build step. The `npx lighthouse` line in the SEO section is a measurement run by hand for the same reason, not a dependency.
- **Six verifiers, all standard library, run by CI on every PR and push to `main`**: `verify_assets.py`, `verify_security.py`, `verify_content.py`, `verify_interactivity.py`, `verify_seo_a11y.py`, `verify_portfolio.py`. Each one pins the acceptance criteria of the issue that created it, so together they are the regression suite this repo has instead of tests. The `verify` workflow runs them and branch protection requires it to pass before a non-admin PR merges; see Continuous integration. Run all six locally before opening a PR as well.
- **No runtime library**: no jQuery, Bootstrap, or Font Awesome since issue #31. `js/main.js` and the inline renderer are vanilla JavaScript, and `verify_security.py` fails a page that loads a script from anywhere but `js/` or a stylesheet from anywhere but `css/` or Google Fonts.
- **Responsive Design**: CSS grid and flex rules in `css/style.css`, with breakpoints at 768px, 992px, and 1200px (the widths the Bootstrap 3 grid used, kept so the layout did not move)
- **Browser Support**: Targets modern browsers with fallbacks for animations
- **Dead CSS remains**: `css/style.css` still holds rules for the removed libraries (`#particles-js`, `.owl-*`, `.mfp-*`, `.home-carousel`, `.testimonial-slider`). Unmatched selectors are harmless. This was previously described here as "tracked separately in issue #18", which was wrong: issue #18 turned out to be the content and navigation issue and did not touch them. No open issue covers this cleanup, so file one before assuming someone else will.
