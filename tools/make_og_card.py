#!/usr/bin/env python3
"""Generate img/og-card.jpg, the 1200x630 card link unfurlers show.

Run from the repository root:

    python3 tools/make_og_card.py

Requires Pillow, like tools/optimize_images.py, and like that script it is run
by hand to regenerate a committed asset. Neither is part of the gate, and
neither runs on the deployed site.

The card is the hero photo the homepage already serves, cropped to the 1.91:1
that every unfurler expects, under the same rgba(0, 0, 0, 0.4) scrim that
css/style.css paints over the hero in .home-1:after, with the same two lines
of copy the hero carries. A shared link then previews as the top of the site
rather than as something assembled separately that can drift away from it.

JPEG, not PNG. Issue 19 asked for a PNG, but this is a photograph: PNG is
lossless and would land near a megabyte at this size, five times the 200 KB
budget the same issue sets, and quantizing it down to fit would band the sky
and the water badly. Every unfurler accepts JPEG. tools/verify_seo_a11y.py
asserts the dimensions and the budget, so whichever format is used has to
hold to both.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "img" / "hero-1280.jpg"
TARGET = ROOT / "img" / "og-card.jpg"

WIDTH, HEIGHT = 1200, 630
SCRIM = 0.4
BUDGET = 200 * 1024

# The page sets Lato, which is fetched from Google Fonts and is not on disk
# here. Open Sans is the closest humanist sans that is, and the fallbacks
# behind it are the two families present on essentially every Linux box. The
# card is generated once and committed, so this chain only has to resolve on
# whatever machine regenerates it.
FONT_CANDIDATES = {
    "bold": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "regular": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def load_font(weight, size):
    for candidate in FONT_CANDIDATES[weight]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(
        "No %s font found. Install fonts-open-sans, or add a path to "
        "FONT_CANDIDATES." % weight
    )


def cover_crop(image, width, height):
    """Scale and center-crop to exactly width x height, preserving aspect.

    The source is 1280x853 (1.50:1) and the target is 1.91:1, so this crops
    off the top and bottom rather than squashing the horizon.
    """
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def main():
    if not SOURCE.exists():
        raise SystemExit("%s is missing; nothing to build the card from." % SOURCE)

    card = cover_crop(Image.open(SOURCE).convert("RGB"), WIDTH, HEIGHT)

    # Same scrim the hero carries, so the text has the same contrast on the
    # card that it has on the page.
    scrim = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    card = Image.blend(card, scrim, SCRIM)

    draw = ImageDraw.Draw(card)
    name_font = load_font("bold", 86)
    role_font = load_font("regular", 40)
    host_font = load_font("bold", 26)

    lines = [
        ("Brad Stricherz", name_font, (255, 255, 255), 236),
        ("Geospatial Software Engineer", role_font, (233, 233, 233), 350),
        ("GEOBRAD.DEV", host_font, (255, 255, 255), 430),
    ]
    for text, font, fill, top in lines:
        # Letter-space the wordmark the way the nav does, by drawing it with
        # spaces between characters rather than reaching for a layout engine.
        if font is host_font:
            text = " ".join(text)
        span = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((WIDTH - (span[2] - span[0])) / 2 - span[0], top),
            text,
            font=font,
            fill=fill,
        )

    card.save(TARGET, "JPEG", quality=82, optimize=True, progressive=True)

    size = TARGET.stat().st_size
    print(
        "%s written: %dx%d, %.1f KB"
        % (TARGET.relative_to(ROOT), WIDTH, HEIGHT, size / 1024.0)
    )
    if size >= BUDGET:
        print("Over the %d KB budget. Lower quality and rerun." % (BUDGET // 1024))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
