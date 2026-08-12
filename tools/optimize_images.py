#!/usr/bin/env python3
"""Regenerate the site's optimized images from their originals.

The originals are deliberately not in the working tree, because one of them is
39 MB. Recover them from git history first:

    git show 3b42a25:img/DSC01590.jpg         > /tmp/DSC01590.jpg
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


# .avatar-hero img renders at 130px, and 170px above the 768px breakpoint.
# 340px is 2x the largest display size, which covers retina.
PORTRAIT_SIZE = 340


def build_portrait(src_dir, out_dir):
    src = os.path.join(src_dir, "PORTRAIT_Cropped.jpg")
    im = Image.open(src).convert("RGB")
    # Aspect-preserving, not a forced square. The current source happens to be
    # square, but forcing it would silently stretch any replacement portrait and
    # make the width/height attributes in index.html encode a wrong ratio.
    out = scaled(im, PORTRAIT_SIZE)
    webp = os.path.join(out_dir, "portrait-340.webp")
    out.save(webp, "WEBP", quality=82, method=6)
    print("wrote %s (%.1f KB)" % (webp, os.path.getsize(webp) / 1024.0))
    jpg = os.path.join(out_dir, "portrait-340.jpg")
    out.save(jpg, "JPEG", quality=82, optimize=True, progressive=True)
    print("wrote %s (%.1f KB)" % (jpg, os.path.getsize(jpg) / 1024.0))


# Both badges render at 60x60 in resume.html. The Cesium mark goes to 2x. The QR
# goes to 4x and stays lossless PNG, because a blurred QR module grid stops
# scanning when a reader zooms in.
CESIUM_SIZE = 120
QR_SIZE = 240


def build_badges(src_dir, out_dir):
    cesium = Image.open(os.path.join(src_dir, "cesium.png")).convert("RGBA")
    out = scaled(cesium, CESIUM_SIZE)
    webp = os.path.join(out_dir, "cesium-120.webp")
    out.save(webp, "WEBP", quality=88, method=6)
    print("wrote %s (%.1f KB)" % (webp, os.path.getsize(webp) / 1024.0))
    png = os.path.join(out_dir, "cesium-120.png")
    out.save(png, "PNG", optimize=True)
    print("wrote %s (%.1f KB)" % (png, os.path.getsize(png) / 1024.0))

    # The QR has a transparent background, and LANCZOS anti-aliasing turns its two
    # tones into a gradient that defeats PNG palette compression: 26.5 KB. A QR is
    # inherently 2-tone, so 16 palette entries carry ample edge shading and cut it
    # to 5.2 KB. FASTOCTREE is used because it is the only Pillow quantizer that
    # accepts RGBA, and the alpha channel has to survive.
    # The QR source is 1680x1670, not square, so this must preserve aspect rather
    # than force 240x240. The width/height attributes in resume.html are set from
    # the dimensions this actually emits.
    qr = Image.open(os.path.join(src_dir, "qr_code.png")).convert("RGBA")
    out = scaled(qr, QR_SIZE)
    out = out.quantize(colors=16, method=Image.Quantize.FASTOCTREE)
    path = os.path.join(out_dir, "qr_code-240.png")
    out.save(path, "PNG", optimize=True)
    print("wrote %s (%.1f KB, %dx%d)" % (
        path, os.path.getsize(path) / 1024.0, out.width, out.height))


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    out_dir = "img"
    build_hero(src_dir, out_dir)
    build_portrait(src_dir, out_dir)
    build_badges(src_dir, out_dir)


if __name__ == "__main__":
    main()
