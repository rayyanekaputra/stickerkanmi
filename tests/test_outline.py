import numpy as np
import pytest
from PIL import Image
from shapely.geometry import Polygon

from conftest import FIXTURES
from stickerkanmi.outline import MIN_CLEARANCE, art_shape, cut_outline

OFFSET, SMOOTH = 30.0, 36.0  # px; ~2.5 / 3 mm at 300 DPI


def alpha_of(name, pad=120):
    a = np.asarray(Image.open(FIXTURES / f"{name}.png").convert("RGBA").getchannel("A"))
    return np.pad(a, pad)


@pytest.mark.parametrize("name", ["thin_details", "glow", "semi_transparent",
                                  "separate_pieces", "donut", "specks", "wide"])
def test_one_polygon_that_clears_the_art(name):
    alpha = alpha_of(name)
    outline = cut_outline(alpha, 10, OFFSET, SMOOTH)
    assert isinstance(outline, Polygon) and outline.is_valid
    assert len(outline.interiors) == 0
    art = art_shape(alpha, 10, 4)
    assert outline.contains(art)
    # Never closer to the art than the guaranteed clearance.
    assert outline.exterior.distance(art) >= OFFSET * MIN_CLEARANCE - 1.5


def test_offset_distance_on_a_disc():
    r = 100
    yy, xx = np.mgrid[:400, :400]
    alpha = (((xx - 200) ** 2 + (yy - 200) ** 2) < r ** 2).astype(np.uint8) * 255
    outline = cut_outline(alpha, 10, OFFSET, SMOOTH)
    d = np.hypot(*(np.asarray(outline.exterior.coords) - 200).T)
    assert d.min() >= r + OFFSET * MIN_CLEARANCE - 2
    assert d.max() <= r + OFFSET + 6


def test_separate_pieces_merge():
    outline = cut_outline(alpha_of("separate_pieces"), 10, OFFSET, SMOOTH)
    art = art_shape(alpha_of("separate_pieces"), 10, 4)
    assert len(art.geoms) == 3
    assert isinstance(outline, Polygon)


def test_holes_only_when_asked_and_big_enough():
    alpha = alpha_of("donut")
    assert len(cut_outline(alpha, 10, OFFSET, SMOOTH, hole_min_px=60).interiors) == 1
    assert len(cut_outline(alpha, 10, OFFSET, SMOOTH, hole_min_px=400).interiors) == 0
    hole = Polygon(cut_outline(alpha, 10, OFFSET, SMOOTH, hole_min_px=60).interiors[0])
    # The hole's cut line stays clear of the ring.
    art = art_shape(alpha, 10, 4)
    assert hole.distance(art.buffer(-1)) >= OFFSET * MIN_CLEARANCE - 1.5


def test_specks_are_ignored():
    art = art_shape(alpha_of("specks"), 10, 4)
    assert isinstance(art, Polygon)
    outline = cut_outline(alpha_of("specks"), 10, OFFSET, SMOOTH)
    # Close-fitting around the square, not dragged out to the noise.
    minx, miny, maxx, maxy = outline.bounds
    assert maxx - minx < 200 + 2 * (OFFSET + SMOOTH)


def test_empty_alpha():
    assert cut_outline(np.zeros((50, 50), np.uint8), 10, OFFSET, SMOOTH).is_empty
