# Homepage Asset Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Note: this plan has more than 5 tasks, which would normally call for
> superpowers:subagent-driven-development. This session operates under a user
> instruction that forbids dispatching subagents, so execution is inline via
> superpowers:executing-plans instead.

**Goal:** Cut homepage transfer from roughly 40 MB to under 1 MB by replacing oversized images with responsive variants and deleting libraries the page never uses.

**Architecture:** Pure asset and markup work. Generate downscaled WebP variants with Pillow, serve the hero through `image-set()` behind width media queries with a single universal JPEG fallback, serve raster `<img>` tags through `<picture>` with explicit `width`/`height`, then delete the five dead JavaScript libraries, their two dead stylesheets, and their now-orphaned init blocks in `js/main.js`. A dependency-free Python checker encodes the acceptance criteria so they cannot silently regress.

**Tech Stack:** Vanilla HTML5, CSS3, jQuery 3.x, Bootstrap 3. Pillow 10.2.0 for image encoding (dev-time only). Python 3 standard library for verification. No build system is introduced.

## Rebase note, 2026-08-12

This plan was written against `16da8af`. It is now re-based onto `b0572b4`, which
added issue #16 (PR #24) and issue #21 (PR #22). Three things changed underneath it:

1. **Task 6 is already done.** Issue #16 rewrote `js/main.js` from 11,848 bytes to
   6,111 and removed every orphaned init block this plan's Task 6 targeted.
   `grep -iE 'owl|magnific|isotope|typer|particles|imagesLoaded|popup'` against
   `origin/main:js/main.js` returns nothing. Task 6 is replaced by a guard that
   asserts the file stays clean; no edit to `js/main.js` is made by this issue.
2. **`js/main.js` is now loaded** by `index.html:467`. Task 8's smoke test therefore
   asserts the site is interactive, not that it is inert. `tools/verify_interactivity.py`
   arrived with issue #16 and must keep exiting 0.
3. **`CLAUDE.md` already documents this issue's end state**, having landed with PR #24
   before the work itself. It is currently wrong about `main`. This branch makes it
   true. Phase 8 verifies every claim in it rather than rewriting it, and the hero
   preload below is taken from CLAUDE.md's description rather than this plan's
   original Step 4, because CLAUDE.md is the stricter and more correct of the two.

No hunk of this plan collides with what landed. Issue #16 touched `css/style.css` only
near line 1209 (`.scroll-up`), far from `.home-1` at 343; it touched `index.html` in the
hero class list, skill bars, portfolio section, and script block, overlapping this plan
only in that the `js/main.js` tag must survive the dead-script deletion.

The four originals are recovered from `3b42a25`, which is still reachable.

## Global Constraints

- No emojis and no em dashes in any file, commit, or comment.
- JavaScript only. Never TypeScript.
- No build system. No npm, webpack, or bundling. `tools/` holds standalone dev-time scripts that the deployed site never executes.
- The hero must look the same to a visitor. This change swaps assets behind an unchanged visual surface; no layout, typography, color, or spacing changes.
- `img/DSC01590.jpg` is removed from the working tree only. It stays recoverable from git history at `3b42a25`. Do not rewrite history.
- Every `<img>` that is touched gains explicit `width` and `height` attributes.
- Absolute asset paths in `css/style.css` keep their leading slash, matching the existing `url('/img/DSC01590.jpg')` convention.

## Measured Baseline

Recorded from the source file on 2026-08-11, used to pick encode settings. WebP, `method=6`:

```
1280x863:  q45=167.2KB  q55=186.9KB  q62=200.6KB  q68=214.4KB
1920x1294: q45=320.6KB  q55=365.0KB  q62=398.1KB  q68=432.4KB
2560x1726: q45=524.6KB  q55=611.2KB  q62=683.6KB  q68=752.4KB
```

Chosen: q62 at all three widths. The 1280 variant is the one phones and typical
laptops download, and at 200.6 KB it satisfies the issue's under-300-KB criterion.
The 1920 and 2560 variants exceed 300 KB and are reached only above those viewport
widths; this tradeoff was approved by the repo owner because 300 KB at 2560 wide is
not reachable at any acceptable quality.

## File Structure

**Created:**
- `tools/verify_assets.py` : dependency-free acceptance-criteria checker. Run by hand, never by the site.
- `tools/optimize_images.py` : one-time asset generator, records exactly how the shipped variants were produced.
- `img/hero-1280.webp`, `img/hero-1920.webp`, `img/hero-2560.webp` : responsive hero variants.
- `img/hero-1280.jpg` : universal fallback for browsers without WebP or `image-set()`.
- `img/portrait-340.webp`, `img/portrait-340.jpg` : avatar at 2x its 170px maximum display width.
- `img/cesium-120.webp`, `img/cesium-120.png` : badge at 2x its 60px display width.
- `img/qr_code-240.png` : QR at 4x display width, kept larger and lossless so the code stays scannable when zoomed.

**Modified:**
- `css/style.css:343-355` : `.home-1` background becomes a responsive `image-set()` stack.
- `index.html:14-32` : drop two dead stylesheet links, add hero preload.
- `index.html:90-92` : avatar becomes a `<picture>` with dimensions and alt text.
- `index.html:461-474` : drop five dead `<script>` tags.
- `resume.html:316-318` : badges become `<picture>` elements with dimensions.
- `js/main.js` : remove init blocks for every library whose file is deleted.
- `privacy.html` : strip per-line leading whitespace, which is 74.3 percent of the file.

**Deleted:**
- `img/DSC01590.jpg` (39,062,417 B), `img/PORTRAIT_Cropped.jpg`, `img/cesium.png`, `img/qr_code.png`
- `js/jquery.magnific-popup.min.js`, `js/owl.carousel.min.js`, `js/jquery.typer.js`, `js/imagesloaded.pkgd.min.js`, `js/isotope.pkgd.min.js`, `js/particles.js`
- `css/magnific-popup.css`, `css/owl.carousel.min.css`

---

### Task 1: Acceptance-criteria checker

This task builds the harness the rest of the plan tests against. Write it first and
watch every assertion fail, so that later tasks have a real red-to-green signal. This
repo has no test runner, so this script is the test suite.

**Files:**
- Create: `tools/verify_assets.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `python3 tools/verify_assets.py` exits 0 when all criteria pass, 1 otherwise. Later tasks call it verbatim. It defines `HOMEPAGE_BUDGET = 1024 * 1024` and `HERO_BUDGET = 300 * 1024`.

- [ ] **Step 1: Write the checker with every acceptance criterion as an assertion**

```python
#!/usr/bin/env python3
"""Check the homepage asset budget from issue 15.

Run from the repository root:

    python3 tools/verify_assets.py

Exits 0 when every criterion holds, 1 otherwise. Standard library only, so it
runs anywhere Python 3 does and adds no build step to the site.
"""

import os
import re
import sys

HOMEPAGE_BUDGET = 1024 * 1024
HERO_BUDGET = 300 * 1024

# Libraries removed because no element on the page keys off them.
DEAD_ASSETS = [
    "js/jquery.magnific-popup.min.js",
    "js/owl.carousel.min.js",
    "js/jquery.typer.js",
    "js/imagesloaded.pkgd.min.js",
    "js/isotope.pkgd.min.js",
    "js/particles.js",
    "css/magnific-popup.css",
    "css/owl.carousel.min.css",
    "img/DSC01590.jpg",
]

# What a first-paint mobile visit to index.html actually pulls down. The 1920 and
# 2560 hero variants are excluded because a mobile viewport never requests them.
HOMEPAGE_ASSETS = [
    "index.html",
    "css/bootstrap.min.css",
    "css/font-awesome.min.css",
    "css/style.css",
    "js/jquery.min.js",
    "js/bootstrap.min.js",
    "img/hero-1280.webp",
    "img/portrait-340.webp",
    "img/favicon.ico",
    "img/Bluesky.svg",
    "fonts/fontawesome-webfont.woff2",
]

failures = []


def check(condition, message):
    if condition:
        print("  PASS  " + message)
    else:
        print("  FAIL  " + message)
        failures.append(message)


def size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def main():
    print("Dead assets removed")
    for path in DEAD_ASSETS:
        check(not os.path.exists(path), "%s is gone" % path)

    print("\nHero budget")
    hero = size("img/hero-1280.webp")
    check(hero > 0, "img/hero-1280.webp exists")
    check(
        0 < hero < HERO_BUDGET,
        "img/hero-1280.webp is %.1f KB, under the %d KB budget"
        % (hero / 1024.0, HERO_BUDGET // 1024),
    )

    print("\nHomepage transfer budget")
    total = sum(size(p) for p in HOMEPAGE_ASSETS)
    for path in HOMEPAGE_ASSETS:
        check(size(path) > 0, "%s exists" % path)
    check(
        total < HOMEPAGE_BUDGET,
        "homepage total is %.1f KB, under the %d KB budget"
        % (total / 1024.0, HOMEPAGE_BUDGET // 1024),
    )

    print("\nNo dead references in markup or CSS")
    for page in ("index.html", "resume.html"):
        body = open(page, encoding="utf-8").read()
        for path in DEAD_ASSETS:
            name = os.path.basename(path)
            check(name not in body, "%s does not reference %s" % (page, name))
    css = open("css/style.css", encoding="utf-8").read()
    check("DSC01590" not in css, "css/style.css does not reference DSC01590")

    print("\nEvery img has explicit width and height")
    for page in ("index.html", "resume.html"):
        body = open(page, encoding="utf-8").read()
        for tag in re.findall(r"<img\b[^>]*>", body):
            has_dims = "width=" in tag and "height=" in tag
            label = re.search(r'src="([^"]*)"', tag)
            label = label.group(1) if label else tag[:40]
            check(has_dims, "%s: <img src=%s> has width and height" % (page, label))

    print("\nprivacy.html is trimmed")
    check(
        0 < size("privacy.html") < 250 * 1024,
        "privacy.html is %.1f KB, under 250 KB" % (size("privacy.html") / 1024.0),
    )

    print("")
    if failures:
        print("%d check(s) failed." % len(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/verify_assets.py`
Expected: exit 1. Every hero, portrait, and dead-asset check FAILs, because nothing has been built or removed yet. This is the red state the remaining tasks turn green.

- [ ] **Step 3: Confirm the failure count is what you expect**

Run: `python3 tools/verify_assets.py; echo "exit=$?"`
Expected: `exit=1`, and the summary line reports a non-zero failure count. Do not proceed until you have seen this output.

---

### Task 2: Generate the responsive hero and wire up the CSS

**Files:**
- Create: `tools/optimize_images.py`, `img/hero-1280.webp`, `img/hero-1920.webp`, `img/hero-2560.webp`, `img/hero-1280.jpg`
- Modify: `css/style.css:343-355`, `index.html` head
- Delete: `img/DSC01590.jpg`

**Interfaces:**
- Consumes: `tools/verify_assets.py` from Task 1.
- Produces: the four hero files listed above. Task 3 extends `tools/optimize_images.py` with the avatar, Task 4 with the badges.

- [ ] **Step 1: Write the generator**

```python
#!/usr/bin/env python3
"""Regenerate the site's optimized images from their originals.

The originals are deliberately not in the working tree, because one of them is
39 MB. Recover them from git history first:

    git show 3b42a25:img/DSC01590.jpg        > /tmp/DSC01590.jpg
    git show 3b42a25:img/PORTRAIT_Cropped.jpg > /tmp/PORTRAIT_Cropped.jpg
    git show 3b42a25:img/cesium.png           > /tmp/cesium.png
    git show 3b42a25:img/qr_code.png          > /tmp/qr_code.png

Then run from the repository root:

    python3 tools/optimize_images.py /tmp

Requires Pillow. This is a dev-time script; the deployed site never runs it.
"""

import os
import sys

from PIL import Image

# WebP quality 62 keeps the 1280 hero at roughly 200 KB, comfortably inside the
# 300 KB budget. The hero sits behind a 40 percent black scrim (.home-1:after),
# so compression artifacts that would show on a bare photo are not visible here.
HERO_QUALITY = 62
HERO_WIDTHS = (1280, 1920, 2560)


def scaled(im, width):
    height = round(im.height * width / im.width)
    return im.resize((width, height), Image.LANCZOS)


def build_hero(src_dir, out_dir):
    src = os.path.join(src_dir, "DSC01590.jpg")
    im = Image.open(src).convert("RGB")
    for width in HERO_WIDTHS:
        out = scaled(im, width)
        path = os.path.join(out_dir, "hero-%d.webp" % width)
        out.save(path, "WEBP", quality=HERO_QUALITY, method=6)
        print("wrote %s (%.1f KB)" % (path, os.path.getsize(path) / 1024.0))
    # One JPEG only. It is the universal fallback for browsers that support
    # neither WebP nor image-set(), which get the 1280 variant at any viewport.
    fallback = scaled(im, 1280)
    path = os.path.join(out_dir, "hero-1280.jpg")
    fallback.save(path, "JPEG", quality=72, optimize=True, progressive=True)
    print("wrote %s (%.1f KB)" % (path, os.path.getsize(path) / 1024.0))


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    out_dir = "img"
    build_hero(src_dir, out_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Recover the original and generate the variants**

```bash
git show 3b42a25:img/DSC01590.jpg > /tmp/DSC01590.jpg
python3 tools/optimize_images.py /tmp
ls -la img/hero-*
```

Expected: `hero-1280.webp` near 200 KB, `hero-1920.webp` near 398 KB, `hero-2560.webp` near 684 KB, `hero-1280.jpg` near 246 KB.

- [ ] **Step 3: Replace the background rule in `css/style.css`**

Replace the `background-image` line inside `.home-1` (currently `css/style.css:347`) and append the two breakpoint rules directly after the `.home-1` block. Keep every other property in `.home-1` untouched.

```css
.home-1 {
    position: relative;
    height: 100%;
    min-height: 550px;
    /* Universal fallback: browsers without image-set() or WebP get the 1280 JPEG
       at every viewport width. */
    background-image: url('/img/hero-1280.jpg');
    background-image: image-set(url('/img/hero-1280.webp') type('image/webp'),
                                url('/img/hero-1280.jpg') type('image/jpeg'));
    background-repeat: no-repeat;
    background-position: center;
    -webkit-background-size: cover;
    -moz-background-size: cover;
    -ms-background-size: cover;
    background-size: cover;
}

/* Larger hero variants are keyed to viewport width, not device pixel ratio. A 3x
   phone is still a small viewport and must not be handed the 2560 file. */
@media screen and (min-width: 1281px) {
    .home-1 {
        background-image: image-set(url('/img/hero-1920.webp') type('image/webp'),
                                    url('/img/hero-1280.jpg') type('image/jpeg'));
    }
}

@media screen and (min-width: 1921px) {
    .home-1 {
        background-image: image-set(url('/img/hero-2560.webp') type('image/webp'),
                                    url('/img/hero-1280.jpg') type('image/jpeg'));
    }
}
```

- [ ] **Step 4: Preload the hero so LCP does not wait on the CSSOM**

A CSS background image is discovered only after the stylesheet parses. Add this to the `<head>` of `index.html`, immediately after the favicon link. The `type` attribute stops non-WebP browsers from downloading a file they cannot use.

One preload per breakpoint, and the `href` values are root-absolute. A preload only
counts if its resolved URL matches the request the CSS makes, and `css/style.css` asks
for `/img/hero-*.webp` with a leading slash. A relative `href` here would resolve to
the same URL only at the site root and would double-fetch anywhere else.

```html
    <!-- Hero background is the LCP element and lives in CSS, so it is not discovered
         until the stylesheet parses. Preload the variant this viewport will actually
         request; the media queries mirror the breakpoints in css/style.css. -->
    <link rel="preload" as="image" href="/img/hero-1280.webp" type="image/webp" media="(max-width: 1280px)">
    <link rel="preload" as="image" href="/img/hero-1920.webp" type="image/webp" media="(min-width: 1281px) and (max-width: 1920px)">
    <link rel="preload" as="image" href="/img/hero-2560.webp" type="image/webp" media="(min-width: 1921px)">
```

- [ ] **Step 5: Delete the 39 MB original**

```bash
git rm img/DSC01590.jpg
```

It remains recoverable from history at `3b42a25`.

- [ ] **Step 6: Verify the hero criteria now pass**

Run: `python3 tools/verify_assets.py 2>&1 | grep -A3 "Hero budget"`
Expected: both hero lines PASS. Total failures drop but do not reach zero yet; the portrait, badge, and privacy checks are still red.

---

### Task 3: Avatar as a picture element

**Files:**
- Modify: `tools/optimize_images.py`, `index.html:90-92`
- Create: `img/portrait-340.webp`, `img/portrait-340.jpg`
- Delete: `img/PORTRAIT_Cropped.jpg`

**Interfaces:**
- Consumes: `build_hero` and `scaled` from Task 2's `tools/optimize_images.py`.
- Produces: `build_portrait(src_dir, out_dir)`, called from `main()`.

The avatar is 1727x1727 and renders at 130px, rising to 170px above the 768px
breakpoint (`css/style.css:416` and `css/style.css:1257`). 340px is 2x its largest
display size.

- [ ] **Step 1: Add the portrait builder to `tools/optimize_images.py`**

Insert this function after `build_hero`, and add `build_portrait(src_dir, out_dir)` to `main()`.

```python
# .avatar-hero img renders at 130px, and 170px above the 768px breakpoint.
# 340px is 2x the largest display size, which covers retina.
PORTRAIT_SIZE = 340


def build_portrait(src_dir, out_dir):
    src = os.path.join(src_dir, "PORTRAIT_Cropped.jpg")
    im = Image.open(src).convert("RGB")
    out = im.resize((PORTRAIT_SIZE, PORTRAIT_SIZE), Image.LANCZOS)
    webp = os.path.join(out_dir, "portrait-340.webp")
    out.save(webp, "WEBP", quality=82, method=6)
    print("wrote %s (%.1f KB)" % (webp, os.path.getsize(webp) / 1024.0))
    jpg = os.path.join(out_dir, "portrait-340.jpg")
    out.save(jpg, "JPEG", quality=82, optimize=True, progressive=True)
    print("wrote %s (%.1f KB)" % (jpg, os.path.getsize(jpg) / 1024.0))
```

- [ ] **Step 2: Generate it**

```bash
git show 3b42a25:img/PORTRAIT_Cropped.jpg > /tmp/PORTRAIT_Cropped.jpg
python3 tools/optimize_images.py /tmp
ls -la img/portrait-340.*
```

Expected: both files well under 40 KB, down from 1,246,395 B.

- [ ] **Step 3: Replace the avatar markup in `index.html`**

Current markup at lines 90 to 92:

```html
            <div class="avatar-hero">
                <img src="img/PORTRAIT_Cropped.jpg">
            </div>
```

Replace with:

```html
            <div class="avatar-hero">
                <picture>
                    <source srcset="img/portrait-340.webp" type="image/webp">
                    <img src="img/portrait-340.jpg" alt="Brad Stricherz" width="340" height="340">
                </picture>
            </div>
```

The `.avatar-hero img` selector is a descendant selector, so it still matches the
`<img>` inside `<picture>` and CSS keeps controlling the rendered width. The
`width` and `height` attributes supply the intrinsic aspect ratio, which is what
prevents layout shift; they do not fight the CSS.

- [ ] **Step 4: Delete the original**

```bash
git rm img/PORTRAIT_Cropped.jpg
```

- [ ] **Step 5: Verify**

Run: `python3 tools/verify_assets.py 2>&1 | grep -i portrait`
Expected: the portrait existence and dimension checks PASS.

---

### Task 4: Resume badges

**Files:**
- Modify: `tools/optimize_images.py`, `resume.html:316-318`
- Create: `img/cesium-120.webp`, `img/cesium-120.png`, `img/qr_code-240.png`
- Delete: `img/cesium.png`, `img/qr_code.png`

**Interfaces:**
- Consumes: `scaled` from Task 2.
- Produces: `build_badges(src_dir, out_dir)`, called from `main()`.

Both badges render at 60x60 via inline styles. The Cesium badge goes to 120px, which
is 2x. The QR goes to 240px and stays lossless, because a QR downscaled to 120px
loses module definition and stops scanning reliably when a reader zooms in.

- [ ] **Step 1: Add the badge builder to `tools/optimize_images.py`**

Insert after `build_portrait`, and add `build_badges(src_dir, out_dir)` to `main()`.

```python
# Both badges render at 60x60 in resume.html. The Cesium mark goes to 2x. The QR
# goes to 4x and stays lossless PNG, because a blurred QR module grid stops
# scanning when a reader zooms in.
CESIUM_SIZE = 120
QR_SIZE = 240


def build_badges(src_dir, out_dir):
    cesium = Image.open(os.path.join(src_dir, "cesium.png")).convert("RGBA")
    out = cesium.resize((CESIUM_SIZE, CESIUM_SIZE), Image.LANCZOS)
    webp = os.path.join(out_dir, "cesium-120.webp")
    out.save(webp, "WEBP", quality=88, method=6)
    print("wrote %s (%.1f KB)" % (webp, os.path.getsize(webp) / 1024.0))
    png = os.path.join(out_dir, "cesium-120.png")
    out.save(png, "PNG", optimize=True)
    print("wrote %s (%.1f KB)" % (png, os.path.getsize(png) / 1024.0))

    qr = Image.open(os.path.join(src_dir, "qr_code.png")).convert("RGBA")
    out = qr.resize((QR_SIZE, QR_SIZE), Image.LANCZOS)
    path = os.path.join(out_dir, "qr_code-240.png")
    out.save(path, "PNG", optimize=True)
    print("wrote %s (%.1f KB)" % (path, os.path.getsize(path) / 1024.0))
```

- [ ] **Step 2: Generate them**

```bash
git show 3b42a25:img/cesium.png  > /tmp/cesium.png
git show 3b42a25:img/qr_code.png > /tmp/qr_code.png
python3 tools/optimize_images.py /tmp
ls -la img/cesium-120.* img/qr_code-240.png
```

Expected: `cesium-120.webp` and `cesium-120.png` in the single-digit KB range, down from 323,881 B. `qr_code-240.png` a few KB, down from 59,231 B.

- [ ] **Step 3: Replace the badge markup in `resume.html`**

Current markup at lines 316 to 318:

```html
            <img src="img/qr_code.png" alt="QR Code" style="height: 60px; width: 60px; object-fit: contain;">
            <img src="img/cesium.png" alt="Cesium Certified Developer"
                 style="height: 60px; width: 60px; object-fit: contain;">
```

Replace with:

```html
            <img src="img/qr_code-240.png" alt="QR Code" width="240" height="240"
                 style="height: 60px; width: 60px; object-fit: contain;">
            <picture>
                <source srcset="img/cesium-120.webp" type="image/webp">
                <img src="img/cesium-120.png" alt="Cesium Certified Developer" width="120" height="120"
                     style="height: 60px; width: 60px; object-fit: contain;">
            </picture>
```

The inline style still wins over the attributes for rendered size. The attributes
exist to give the browser an aspect ratio before the bytes arrive.

- [ ] **Step 4: Delete the originals**

```bash
git rm img/cesium.png img/qr_code.png
```

- [ ] **Step 5: Verify**

Run: `python3 tools/verify_assets.py 2>&1 | grep -i "cesium\|qr_code"`
Expected: the removal checks and the resume.html dimension checks PASS.

---

### Task 5: Delete the dead libraries

Five `<script>` tags and two `<link>` tags load libraries that no element on the
page keys off. Verified by grepping every selector each library binds to:
`popup-link`, `popup-youtube`, `home-carousel`, `testimonial-slider`,
`filtr-container`, and `particles-js` all return zero matches in `index.html` and
`resume.html`. `js/particles.js` is not loaded by any page at all.

**Files:**
- Modify: `index.html:14-32`, `index.html:461-474`
- Delete: `js/jquery.magnific-popup.min.js`, `js/owl.carousel.min.js`, `js/jquery.typer.js`, `js/imagesloaded.pkgd.min.js`, `js/isotope.pkgd.min.js`, `js/particles.js`, `css/magnific-popup.css`, `css/owl.carousel.min.css`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Task 6 removes the init code these libraries backed.

- [ ] **Step 1: Confirm the selectors are still absent before deleting anything**

```bash
for s in popup-link popup-youtube home-carousel testimonial-slider filtr-container particles-js; do
  printf "%-22s %s\n" "$s" "$(grep -c "$s" index.html resume.html | paste -sd' ')"
done
```

Expected: every count is 0. If any is non-zero, stop and reassess; the library is live.

- [ ] **Step 2: Remove the two dead stylesheet links from the `<head>`**

Delete these lines and their preceding comments from `index.html` (currently lines 16 to 21):

```html
    <!-- Magnific Popup CSS -->
    <link rel="stylesheet" href="css/magnific-popup.css">

    <!-- Owl Carousel CSS -->
    <link rel="stylesheet" href="css/owl.carousel.min.css">
```

Neither is referenced: `grep -c "mfp-\|owl-" index.html` returns 0.

- [ ] **Step 3: Remove the five dead script tags**

Delete these lines and their comments from `index.html` (currently lines 464 to 474), keeping `jquery.min.js` and `bootstrap.min.js`:

```html
<!-- Magnific Popup core JS file -->
<script src="js/jquery.magnific-popup.min.js"></script>
<!-- Owl Carousel JS -->
<script src="js/owl.carousel.min.js"></script>
<!-- jQuery Typer JS -->
<script src="js/jquery.typer.js"></script>
<!-- jQuery Images Loaded JS -->
<script src="js/imagesloaded.pkgd.min.js"></script>
<!-- jQuery Filterizr JS -->
<script src="js/isotope.pkgd.min.js"></script>
```

Leave the `.typer-title` class on the `<h2>` at `index.html:94`. It carries styling from `css/style.css`; only the never-initialized library goes.

- [ ] **Step 4: Delete the files**

```bash
git rm js/jquery.magnific-popup.min.js js/owl.carousel.min.js js/jquery.typer.js \
       js/imagesloaded.pkgd.min.js js/isotope.pkgd.min.js js/particles.js \
       css/magnific-popup.css css/owl.carousel.min.css
```

- [ ] **Step 5: Verify no reference survives**

Run: `python3 tools/verify_assets.py 2>&1 | grep -i "does not reference\|is gone"`
Expected: every one of these lines PASSes.

---

### Task 6: Guard that js/main.js references no deleted library

Superseded. Issue #16 (PR #24, merged as `5cf42a5`) already deleted every orphaned
init block this task was written to remove. `js/main.js` went from 11,848 bytes to
6,111 and now holds only the sticky nav, smooth scroll, active-link tracking, mobile
nav collapse, scroll-to-top button, and skill bars, each with a matching element in
`index.html`.

This task no longer edits anything. It asserts the premise Task 5 depends on: that
deleting the six library files leaves no caller behind. Run it after Task 5, and stop
if it fails, because a surviving `.magnificPopup()` call would throw a TypeError that
aborts every initializer after it in the single `$(function(){ ... })` handler.

**Files:** none. This task only verifies.

**Interfaces:**
- Consumes: Task 5's deletions.
- Produces: nothing.

- [ ] **Step 1: Confirm no deleted library is called**

```bash
grep -nE "magnificPopup|owlCarousel|isotope|imagesLoaded|particlesJS|\.typer\(" js/main.js index.html resume.html
```

Expected: no matches, exit status 1. Any match means a caller outlived its library.

- [ ] **Step 2: Confirm the file still parses**

```bash
node --check js/main.js
```

Expected: no output, exit 0.

- [ ] **Step 3: Confirm the live initializers are intact**

```bash
python3 tools/verify_interactivity.py; echo "exit=$?"
```

Expected: `exit=0`. This is issue #16's checker; it asserts every function in
`js/main.js` still has the element it targets. This issue must not regress it.

---

### Task 7: Trim privacy.html

632,542 bytes across 3,542 lines, of which 470,262 bytes, or 74.3 percent, is
per-line leading whitespace. The two `<style>` blocks the issue points at are tiny
(lines 1 to 42 and 3512 to 3528); indentation is the actual weight.

Stripping leading whitespace while keeping the newline is safe here because the
newline still collapses to a single space in inline contexts, and the file contains
no `<pre>`, no `<textarea>`, and no `white-space` declaration. Verified:
`grep -c "<pre\|<textarea\|white-space" privacy.html` returns 0.

**Files:**
- Modify: `privacy.html`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Write the equivalence test before touching the file**

This proves the trim changes no rendered text. Save as `/tmp/check_privacy.py`; it is a one-shot check and does not belong in the repo.

```python
#!/usr/bin/env python3
"""Assert that trimming privacy.html leaves its rendered text unchanged."""

import re
import sys
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.chunks.append(data)

    def text(self):
        return re.sub(r"\s+", " ", "".join(self.chunks)).strip()


def extract(path):
    parser = TextExtractor()
    parser.feed(open(path, encoding="utf-8").read())
    return parser.text()


before, after = sys.argv[1], sys.argv[2]
a, b = extract(before), extract(after)
if a == b:
    print("PASS: rendered text identical (%d chars)" % len(a))
    sys.exit(0)
print("FAIL: rendered text differs (%d vs %d chars)" % (len(a), len(b)))
for i, (x, y) in enumerate(zip(a, b)):
    if x != y:
        print("first difference at char %d: %r vs %r" % (i, a[i:i+60], b[i:i+60]))
        break
sys.exit(1)
```

- [ ] **Step 2: Snapshot the original and confirm the test passes against itself**

```bash
cp privacy.html /tmp/privacy-before.html
python3 /tmp/check_privacy.py /tmp/privacy-before.html privacy.html
```

Expected: PASS. This confirms the test is wired correctly before it has anything to catch.

- [ ] **Step 3: Strip the leading whitespace**

```bash
python3 - <<'PY'
lines = open('privacy.html', encoding='utf-8').read().split('\n')
out = '\n'.join(line.lstrip() for line in lines)
open('privacy.html', 'w', encoding='utf-8').write(out)
PY
```

- [ ] **Step 4: Confirm the rendered text is unchanged**

```bash
python3 /tmp/check_privacy.py /tmp/privacy-before.html privacy.html
ls -la privacy.html
```

Expected: PASS, and the file drops from 632,542 B to roughly 162 KB. If it FAILs, restore with `git checkout privacy.html` and stop; something in the file depends on leading whitespace after all.

- [ ] **Step 5: Verify against the checker**

Run: `python3 tools/verify_assets.py 2>&1 | grep -i privacy`
Expected: PASS.

---

### Task 8: Full verification and Lighthouse

**Files:** none. This task only measures.

**Interfaces:**
- Consumes: everything above.
- Produces: the evidence block for the pull request body.

- [ ] **Step 1: Run both checkers**

```bash
python3 tools/verify_assets.py; echo "assets exit=$?"
python3 tools/verify_interactivity.py; echo "interactivity exit=$?"
```

Expected: both `exit=0`, and `All checks passed.` from the first. Every criterion from
issue 15 that can be measured statically is green, and issue #16's interactivity
contract is unbroken. If anything is red, fix it before continuing rather than
proceeding to the browser.

- [ ] **Step 2: Serve the site**

```bash
python3 -m http.server 8123 >/dev/null 2>&1 &
```

Port 8123 rather than the 8000 in CLAUDE.md, to avoid colliding with anything the user is already running. Remember to stop it at the end.

- [ ] **Step 3: Confirm every homepage asset returns 200**

```bash
for p in / /css/style.css /js/jquery.min.js /js/main.js /img/hero-1280.webp /img/portrait-340.jpg /resume.html; do
  printf "%-28s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://localhost:8123$p)"
done
```

Expected: `200` for every path. `/js/main.js` is now referenced by `index.html:467`, so a 404 there breaks the live site. Any 404 means a rename was missed in markup.

- [ ] **Step 4: Confirm the removed files 404**

```bash
for p in /img/DSC01590.jpg /js/owl.carousel.min.js /css/magnific-popup.css; do
  printf "%-32s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8123$p)"
done
```

Expected: `404` for all three.

- [ ] **Step 5: Drive the pages in a browser**

Load `http://localhost:8123/` and `http://localhost:8123/resume.html`. Confirm by eye and by console:
- The hero background renders and looks the same as before.
- The avatar renders round and correctly sized, with no layout shift on load.
- Both resume badges render at 60x60.
- The browser console is free of errors, in particular any `is not a function` TypeError from a library this issue deleted.
- Scroll the homepage and confirm the site is still interactive, since `js/main.js` now runs: the navbar goes sticky past 100px, nav links smooth-scroll to their sections and highlight the active one, the scroll-to-top button appears past 1000px and works, and the skill bars animate from 5% to their `data-percent` widths when the portfolio section scrolls into view.
- There is no parallax and there must not be one; issue #16 removed it deliberately because `background-size: cover` exposes blank space when the position shifts.

- [ ] **Step 6: Run Lighthouse on mobile**

Run a mobile Lighthouse audit against `http://localhost:8123/`. Record the performance score and the LCP value. The acceptance criterion is a performance score above 90.

If the score falls short, capture which audit is responsible before changing anything. Likely candidates, in order: render-blocking `css/bootstrap.min.css` at 121 KB, the Google Fonts stylesheet at `index.html:29`, and the two `oss.maxcdn.com` shims at `index.html:37-38`. Report the finding rather than expanding scope unilaterally; those are separate concerns from this issue.

- [ ] **Step 7: Stop the server**

```bash
kill %1
```

- [ ] **Step 8: Record the before and after numbers**

```bash
git diff --stat origin/main
du -sh img/
```

Capture the total bytes removed for the pull request body.

---

## Self-Review

**Spec coverage.** Every acceptance criterion in issue 15 maps to a task:

| Criterion | Task |
|---|---|
| Homepage total transfer under 1 MB | 1 (assertion), 2, 3, 5 |
| Hero under 300 KB and served responsively | 2 |
| All images have explicit width/height | 1 (assertion), 3, 4 |
| No script tag loads an unused library | 5, 6 (guard only; #16 did the js/main.js half) |
| Lighthouse mobile above 90 | 8 |

**Assets already generated.** Tasks 2, 3, and 4 each say "generate", but the nine
optimized files and `tools/optimize_images.py` already exist, carried over from the
run against `16da8af` and byte-verified before reuse: hero 1280/1920/2560 WebP at
205,402 / 407,640 / 699,984 B with the JPEG fallback at 251,957 B, `portrait-340`
at 340x340, `cesium-120` at 120x120, `qr_code-240` at 240x239. Re-running the
generator is optional and only needed if an encode setting changes; the reuse is
sound because the script is deterministic and its inputs are fixed blobs in history.

Issue findings 1 through 5 map to tasks 2, 3, 4, 5, and 7 respectively. Finding 6,
the PDF, needs no task: it is already 49,042 B, not the 596 KB the issue reports,
having been shrunk by commit `b251bfe`. This must be stated in the pull request body
so the stale finding is not left looking unaddressed.

**Placeholder scan.** No TBDs, no "add error handling", no "similar to Task N". Every
code step carries the literal content to write.

**Type consistency.** `tools/optimize_images.py` grows across tasks 2, 3, and 4;
`scaled()` is defined once in Task 2 and reused by both later tasks; `build_hero`,
`build_portrait`, and `build_badges` all take `(src_dir, out_dir)` and all are added
to the same `main()`. `tools/verify_assets.py` filenames match the filenames the
generators emit: `hero-1280.webp`, `portrait-340.webp`, `cesium-120.webp`,
`qr_code-240.png`.

**One known gap.** `tools/verify_assets.py` asserts `width` and `height` on every
`<img>` in both pages, but tasks 3 and 4 only touch the four raster images. If either
page holds another `<img>`, that assertion fails in Task 8 through no fault of the
plan. `index.html:168` and `index.html:431` both carry `./img/Bluesky.svg`. Add
`width="20" height="20"` to both when Task 8 Step 1 flags them, matching their
rendered size. This is a two-line change, not a new task.
