"""Generate the synthetic problem images in tests/fixtures/problems/.

Run from the project root:  .venv/bin/python tests/fixtures/make_fixtures.py
Each one targets an edge case the outline has to survive.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).parent / "problems"
N = 400


def canvas():
    return Image.new("RGBA", (N, N), (0, 0, 0, 0))


def thin_details():
    """A blob with hair-thin antennae: the line must not clip them."""
    im = canvas()
    d = ImageDraw.Draw(im)
    d.ellipse((120, 160, 280, 320), fill=(40, 140, 60, 255))
    d.line((170, 170, 110, 40), fill=(40, 140, 60, 255), width=3)
    d.line((230, 170, 300, 50), fill=(40, 140, 60, 255), width=3)
    return im


def glow():
    """Solid star with a soft glow fading to transparent."""
    im = canvas()
    pts = [(200 + r * np.cos(a), 200 + r * np.sin(a))
           for i, a in enumerate(np.linspace(-np.pi / 2, 1.5 * np.pi, 10, endpoint=False))
           for r in [130 if i % 2 == 0 else 55]]
    # Blur only the alpha: blurring RGBA mixes in the transparent black.
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    halo = Image.new("RGBA", (N, N), (255, 200, 0, 0))
    halo.putalpha(mask.filter(ImageFilter.GaussianBlur(18)))
    im.alpha_composite(halo)
    ImageDraw.Draw(im).polygon(pts, fill=(240, 160, 0, 255))
    return im


def semi_transparent():
    """Opaque square with a 40%-alpha 'shadow' panel beside it."""
    im = canvas()
    d = ImageDraw.Draw(im)
    d.rectangle((60, 60, 220, 220), fill=(30, 30, 160, 255))
    over = canvas()
    ImageDraw.Draw(over).rectangle((180, 180, 340, 340), fill=(30, 30, 160, 100))
    im.alpha_composite(over)
    return im


def separate_pieces():
    """Three dots far apart: must still get one outer contour."""
    im = canvas()
    d = ImageDraw.Draw(im)
    for x, y in [(80, 80), (310, 120), (190, 320)]:
        d.ellipse((x - 45, y - 45, x + 45, y + 45), fill=(200, 40, 80, 255))
    return im


def donut():
    """A ring with a big hole: only cut with --holes."""
    im = canvas()
    d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 380, 380), fill=(150, 90, 40, 255))
    d.ellipse((110, 110, 290, 290), fill=(0, 0, 0, 0))
    return im


def specks():
    """Art plus stray near-invisible noise pixels that must be ignored."""
    im = canvas()
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((100, 100, 300, 300), 30, fill=(90, 50, 150, 255))
    rng = np.random.default_rng(1)
    a = np.array(im)
    for x, y in rng.integers(0, N, size=(12, 2)):
        if not (90 < x < 310 and 90 < y < 310):
            a[y, x] = (90, 50, 150, 60)
    return Image.fromarray(a)


def wide():
    """A wide banner: auto-rotate should turn it in a tall cell."""
    im = Image.new("RGBA", (600, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((10, 10, 590, 150), 40, fill=(20, 120, 180, 255))
    return im


def tiny():
    """A 32px raster: should trigger the 'upscaled, may print soft' note."""
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((2, 2, 29, 29), fill=(220, 60, 60, 255))
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [("thin_details", thin_details), ("glow", glow),
                     ("semi_transparent", semi_transparent), ("separate_pieces", separate_pieces),
                     ("donut", donut), ("specks", specks), ("wide", wide), ("tiny", tiny)]:
        fn().save(OUT / f"{name}.png")
        print(f"wrote {OUT / name}.png")


if __name__ == "__main__":
    main()
