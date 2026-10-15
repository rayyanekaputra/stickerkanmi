import pytest

from sticker_maker.config import SheetConfig, StickerSpec
from sticker_maker.layout import LayoutError, expand_copies, guide_gap_warning, make_grid
from sticker_maker.units import mm_to_px


def test_stretched_grid_fills_page_inside_margins():
    cfg = SheetConfig(grid=(3, 5))
    g = make_grid(cfg)
    m = mm_to_px(cfg.margin, cfg.dpi)
    x, y, w, h = g.cell(0)
    assert x == pytest.approx(m) and y == pytest.approx(m)
    x, y, w, h = g.cell(14)
    assert x + w == pytest.approx(g.page_w - m)
    assert y + h == pytest.approx(g.page_h - m)


def test_auto_grid_fits_as_many_as_possible():
    # A4 minus 6 mm margins = 198 x 285 mm; 40 mm cells with 4 mm gaps.
    g = make_grid(SheetConfig(grid=None, size=(40, 40)))
    assert (g.cols, g.rows) == (4, 6)
    x, y, w, h = g.cell(0)
    assert w == pytest.approx(mm_to_px(40, 300))
    # Block is centred.
    assert x == pytest.approx(g.page_w - (g.cell(3)[0] + w))


def test_fixed_grid_too_big_errors():
    with pytest.raises(LayoutError):
        make_grid(SheetConfig(grid=(6, 6), size=(50, 50)))


def test_auto_without_size_errors():
    with pytest.raises(LayoutError):
        make_grid(SheetConfig(grid=None))


def test_guide_box_is_centred_in_gap():
    cfg = SheetConfig(grid=(2, 2), gap=4)
    g = make_grid(cfg)
    right_of_first = g.guide_box(0)[0] + g.guide_box(0)[2]
    left_of_second = g.guide_box(1)[0]
    assert right_of_first == pytest.approx(left_of_second)


def test_gap_warning():
    assert guide_gap_warning(SheetConfig(gap=1.5))
    assert guide_gap_warning(SheetConfig(gap=1.5, grid_lines="none")) is None
    assert guide_gap_warning(SheetConfig(gap=4)) is None


def test_copies_and_fill_page():
    a, b = StickerSpec("a", copies=2), StickerSpec("b")
    assert [s.path for s in expand_copies([a, b], 9, False)] == ["a", "a", "b"]
    filled = expand_copies([a, b], 4, True)
    assert len(filled) == 4
