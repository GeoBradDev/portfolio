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
    # Oversized image originals, all four replaced by responsive variants.
    "img/DSC01590.jpg",
    "img/PORTRAIT_Cropped.jpg",
    "img/cesium.png",
    "img/qr_code.png",
]

# Basenames that must not appear anywhere in css/style.css. Only the two the
# stylesheet ever referenced are listed. The badges live in resume.html, which
# carries its own inline <style>, so asserting their absence here would be an
# assertion that cannot fail; the markup scan below is what actually covers them.
DEAD_CSS_REFERENCES = ["DSC01590", "PORTRAIT_Cropped"]

# Every optimized variant the site now ships. A typo in a CSS or markup path would
# otherwise pass every other check in this file.
SHIPPED_VARIANTS = [
    "img/hero-1280.webp",
    "img/hero-1920.webp",
    "img/hero-2560.webp",
    # Not in the transfer budget below, because only a browser without WebP asks
    # for it, but it is the universal fallback and must never go missing.
    "img/hero-1280.jpg",
    "img/portrait-340.webp",
    "img/portrait-340.jpg",
    "img/cesium-120.webp",
    "img/cesium-120.png",
    "img/qr_code-240.png",
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
    "js/main.js",
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

    print("\nShipped variants present")
    for path in SHIPPED_VARIANTS:
        check(size(path) > 0, "%s exists" % path)

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
    for name in DEAD_CSS_REFERENCES:
        check(name not in css, "css/style.css does not reference %s" % name)

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
