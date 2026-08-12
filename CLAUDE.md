# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static portfolio website for GeoBrad.dev (Brad Stricherz) - a geospatial software developer's personal site. Deployed to GitHub Pages at www.geobrad.dev.

## Technology Stack

- **Frontend**: Vanilla HTML5, CSS3, JavaScript (jQuery-based)
- **CSS Framework**: Bootstrap 3.x
- **Key Libraries**:
  - jQuery 3.x (js/jquery.min.js)
  - Bootstrap JS (js/bootstrap.min.js)
- **Deployment**: GitHub Pages with custom domain (CNAME)

Owl Carousel, Magnific Popup, Isotope, imagesLoaded, jQuery Typer, and Particles.js
were removed in issue #15. None of them had a matching element on any page, so all
of them downloaded and did nothing. Do not reintroduce a library without an element
that actually uses it.

## Site Structure

- `index.html` - Main portfolio page with sections: home, about, services, portfolio, contact
- `resume.html` - Interactive resume with dark mode toggle
- `privacy.html` - Privacy policy page (158KB)
- `css/style.css` - Main custom styles
- `js/main.js` - Navigation, scroll, and skill-bar logic. Loaded by `index.html` only.
- `img/` - Images including profile photo, badges (Cesium certification, QR code)
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
The portfolio section in index.html (script at lines 469-882, embedded styles at 579-871) dynamically fetches and displays GitHub repositories:
- Fetches repos from multiple GitHub users: GeoBradDev, MapTheVoteSTL, Seaside-Sustainability-Web-GIS
- Filters repositories containing "portfolio" in description
- Displays cards with repo name, language, stars, description, and links
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

### Visual Effects
- No parallax. See the `js/main.js` section above for why it was removed.
- Skill bars for the skills section, driven by `progressBars()`
- Hover effects and transitions throughout

### Responsive Hero Background
`.home-1` in `css/style.css:343-381` serves the hero through three viewport-width
breakpoints, not device pixel ratio. Keying on DPR would hand a 3x phone the 2560
file, which is the opposite of what is wanted.

| Viewport | File | Size |
|---|---|---|
| up to 1280px | `img/hero-1280.webp` | 200.6 KB |
| 1281px to 1920px | `img/hero-1920.webp` | 398.1 KB |
| 1921px and up | `img/hero-2560.webp` | 683.6 KB |

`img/hero-1280.jpg` is the universal fallback in the base rule, for browsers with
neither WebP nor `image-set()`. Each breakpoint also carries a `-webkit-image-set()`
line for Safari 14 to 16, which support WebP but not the `type()` notation.

Do not replace those breakpoint rules with a plain `url('...webp')` declaration. A
browser lacking both WebP and `image-set()` would then receive an undecodable file
instead of falling back to the JPEG.

`index.html` preloads the matching variant per breakpoint, because a CSS background
image is not discovered until the stylesheet parses, and this one is the LCP element.
The preload `href` values are root-absolute to match the URLs in `css/style.css`; a
preload only counts if its resolved URL matches the request the CSS makes.

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
oversized original returns, every `<img>` carries explicit `width`/`height`, the hero
stays under 300 KB, and the homepage stays under 1 MB. Standard library only. Run it
after touching any asset, markup `<img>` tag, or `<script>`/`<link>` tag.

### Regenerating optimized images

```bash
python3 tools/optimize_images.py /tmp
```

The originals are deliberately not in the working tree, because one was 39 MB. The
script's docstring lists the `git show 3b42a25:img/...` commands that recover them.
Requires Pillow. Never commit a full-resolution camera original.

### Making Changes

**HTML Files**: Edit directly - no build step needed

**CSS Changes**:
- Main styles: `css/style.css`
- Some critical CSS is embedded in `index.html` (portfolio section styles)

**JavaScript Changes**:
- Main logic: `js/main.js`
- Some inline JavaScript in `index.html` (portfolio loading logic at lines 469-882)

**Important**: When modifying the portfolio loading logic in index.html, the JavaScript and CSS are both inline. The portfolio cards system includes both functionality and styles in the same section.

### GitHub API Rate Limiting
The portfolio section fetches from GitHub API. Be aware:
- Unauthenticated requests have 60 requests/hour limit
- Error handling is implemented (the `catch` at index.html:567)
- Consider this when testing portfolio loading features

## Common Tasks

### Updating Portfolio Content
Portfolio items are automatically pulled from GitHub repos with "portfolio" in the description. To add/modify:
1. Update the repo's description on GitHub to include "portfolio"
2. Site will automatically show it on next load

### Updating Resume
Edit `resume.html` - it's a standalone HTML file with inline styles and JavaScript.

### Modifying Contact Form
The form submits to FormSubmit (line 393 in index.html). To change:
- Update the action URL with new FormSubmit endpoint
- Honeypot field is present for spam protection (line 410)

### Adding/Changing Images
Every raster image ships at roughly 2x its largest CSS display size, as WebP with a
fallback, and every `<img>` carries explicit `width`/`height` to prevent layout shift.

- Hero background: `img/hero-{1280,1920,2560}.webp` plus `img/hero-1280.jpg`, wired in `css/style.css:343-381`
- Profile avatar: `img/portrait-340.{webp,jpg}` in a `<picture>` at `index.html:90`
- Badges: `img/cesium-120.{webp,png}` and `img/qr_code-240.png` at `resume.html:318`
- Social icons: `img/Bluesky.svg`

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

- **No Build System**: This is intentional - keep it simple with no npm/webpack/bundling. `tools/` holds standalone scripts run by hand, not a build step.
- **jQuery Dependency**: The entire site relies on jQuery. Modern JavaScript refactoring would require significant rewrite
- **Bootstrap 3**: Using older Bootstrap version. Upgrading requires CSS/HTML updates
- **Responsive Design**: Mobile-responsive via Bootstrap grid and custom media queries
- **Browser Support**: Targets modern browsers with fallbacks for animations
- **Dead CSS remains**: `css/style.css` still holds rules for the removed libraries (`#particles-js`, `.owl-*`, `.mfp-*`, `.home-carousel`, `.testimonial-slider`). Unmatched selectors are harmless; cleanup is tracked separately in issue #18.
