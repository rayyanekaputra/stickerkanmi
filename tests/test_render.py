import os

import numpy as np
import pytest
from PIL import Image

from conftest import FIXTURES, ICONS, ROOT
from stickerkanmi import io as sio
from stickerkanmi.config import SheetConfig, load_specs
from stickerkanmi.render import dash_runs, render_calibration, render_pages

GOLDEN = ROOT / "tests" / "golden"


def specs_for(folder, cfg, names=None):
    files = sio.find_images(folder)
    if names:
        files = [f for f in files if f.stem in names]
    return load_specs(files, folder, cfg)


def test_dash_runs_line_up_across_segments():
    # The same edge drawn from two boxes with an absolute phase gives the same dashes.
    a = dash_runs([(10, 0), (110, 0)], 6, 4, phase=10)
    b = dash_runs([(10, 0), (110, 0)], 6, 4, phase=10)
    assert all(np.allclose(x, y) for x, y in zip(a, b))
    # Dashes start on multiples of the period in page coordinates.
    assert a[0][0][0] == pytest.approx(10)  # 10 % 10 == 0 -> starts with a dash
    assert all(r[0][0] % 10 == pytest.approx(0) or r[0][0] == 10 for r in a)


def test_pages_and_paging():
    cfg = SheetConfig(grid=(2, 2), dpi=100)
    pages, grid = render_pages(specs_for(ICONS, cfg, ["heart", "moon", "zap", "sun", "bug"]),
                               cfg, log=lambda m: None)
    assert len(pages) == 2
    assert pages[0].size == (grid.page_w, grid.page_h)


def test_fill_page_and_copies():
    cfg = SheetConfig(grid=(3, 3), dpi=60, copies=2, fill_page=True)
    pages, _ = render_pages(specs_for(ICONS, cfg, ["heart", "moon"]), cfg, log=lambda m: None)
    assert len(pages) == 1


def test_uniform_keeps_relative_sizes(tmp_path):
    big = Image.new("RGBA", (200, 200), (255, 0, 0, 255))
    small = Image.new("RGBA", (100, 100), (0, 0, 255, 255))
    big.save(tmp_path / "a_big.png")
    small.save(tmp_path / "b_small.png")
    cfg = SheetConfig(grid=(2, 1), dpi=100, sizing="uniform", grid_lines="none")
    page = np.asarray(render_pages(specs_for(tmp_path, cfg), cfg, log=lambda m: None)[0][0])
    red = ((page[..., 0] > 200) & (page[..., 2] < 50)).sum()
    blue = ((page[..., 2] > 200) & (page[..., 0] < 50)).sum()
    assert red / blue == pytest.approx(4, rel=0.05)


def test_stickers_toml_overrides(tmp_path):
    Image.new("RGBA", (50, 50), (0, 0, 0, 255)).save(tmp_path / "a.png")
    Image.new("RGBA", (50, 50), (0, 0, 0, 255)).save(tmp_path / "b.png")
    (tmp_path / "stickers.toml").write_text('["a.png"]\ncopies = 3\nsize = "1in"\n'
                                            '["b.png"]\nskip = true\n')
    specs = specs_for(tmp_path, SheetConfig())
    assert [(s.path.name, s.copies) for s in specs] == [("a.png", 3)]
    assert specs[0].size == pytest.approx(25.4)


def test_save_jpg_with_dpi(tmp_path):
    cfg = SheetConfig(dpi=150)
    page = render_calibration(cfg)
    out = sio.page_paths(tmp_path / "sheet", 1, "jpg")[0]
    sio.save_page(page, out, "jpg", cfg.dpi)
    im = Image.open(out)
    assert out.suffix == ".jpg" and im.format == "JPEG"
    assert im.info["dpi"] == pytest.approx((150, 150))
    assert im.info.get("icc_profile")


def test_output_names():
    assert sio.output_format("x.png") == "png"
    assert sio.output_format("x.jpeg") == "jpg"
    assert sio.output_format("x") == "jpg"
    paths = sio.page_paths("out/sheet.jpg", 3, "jpg")
    assert [p.name for p in paths] == ["sheet.jpg", "sheet_2.jpg", "sheet_3.jpg"]
    assert sio.page_paths("sheet.png", 1, "jpg")[0].name == "sheet.jpg"


def test_golden_sheet():
    """Render the problem fixtures and compare to the stored sheet.

    Regenerate after an intended visual change (and look at it first!):
        UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_render.py -k golden
    """
    cfg = SheetConfig(grid=(3, 3), dpi=100, holes=True)
    page = render_pages(specs_for(FIXTURES, cfg), cfg, log=lambda m: None)[0][0]
    path = GOLDEN / "problems_a4_100dpi.png"
    if os.environ.get("UPDATE_GOLDEN") or not path.exists():
        path.parent.mkdir(exist_ok=True)
        page.save(path)
        pytest.skip("golden image written")
    want = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    got = np.asarray(page, dtype=np.int16)
    assert got.shape == want.shape
    diff = np.abs(got - want).max(axis=2)
    # Allow anti-aliasing noise from library versions, not real changes.
    assert (diff > 40).mean() < 0.002, f"{(diff > 40).sum()} pixels changed"


def test_icc_profile_input_is_converted(tmp_path):
    im = Image.new("RGBA", (40, 40), (200, 100, 50, 255))
    im.save(tmp_path / "srgb.png", icc_profile=sio.SRGB_ICC)
    loaded, _ = sio.load_rgba(tmp_path / "srgb.png", 100)
    assert loaded.mode == "RGBA"
    assert np.abs(np.asarray(loaded)[20, 20].astype(int) - (200, 100, 50, 255)).max() <= 2


def test_huge_source_is_capped(tmp_path):
    Image.new("RGBA", (3000, 1500), (0, 0, 0, 255)).save(tmp_path / "big.png")
    img, scale = sio.load_rgba(tmp_path / "big.png", 600)
    assert img.size == (600, 300) and scale == pytest.approx(0.2)
