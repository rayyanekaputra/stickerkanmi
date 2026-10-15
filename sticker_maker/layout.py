"""Paper sizes, grid math, cell placement and paging. Pixels at the output DPI."""

import math
from dataclasses import dataclass

from .units import format_length, mm_to_px, px_to_mm

PAPER_MM = {
    "a3": (297, 420),
    "a4": (210, 297),
    "a5": (148, 210),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
}

MIN_GUIDE_GAP_MM = 2.0  # below this the dashed box lines crowd the cut line


class LayoutError(ValueError):
    pass


@dataclass
class Grid:
    page_w: int
    page_h: int
    cols: int
    rows: int
    cell_w: float
    cell_h: float
    gap: float
    x0: float  # left edge of the first cell
    y0: float

    @property
    def per_page(self):
        return self.cols * self.rows

    def cell(self, i):
        """(x, y, w, h) of the i-th cell on a page, row by row."""
        r, c = divmod(i, self.cols)
        return (self.x0 + c * (self.cell_w + self.gap), self.y0 + r * (self.cell_h + self.gap),
                self.cell_w, self.cell_h)

    def guide_box(self, i):
        """The cell grown by half the gap: its rough-cut box."""
        x, y, w, h = self.cell(i)
        g = self.gap / 2
        return x - g, y - g, w + 2 * g, h + 2 * g


def page_size_px(cfg):
    w_mm, h_mm = PAPER_MM[cfg.paper]
    if cfg.landscape:
        w_mm, h_mm = h_mm, w_mm
    return round(mm_to_px(w_mm, cfg.dpi)), round(mm_to_px(h_mm, cfg.dpi))


def make_grid(cfg):
    dpi = cfg.dpi
    page_w, page_h = page_size_px(cfg)
    margin, gap = mm_to_px(cfg.margin, dpi), mm_to_px(cfg.gap, dpi)
    avail_w, avail_h = page_w - 2 * margin, page_h - 2 * margin
    fmt = lambda mm: format_length(mm, cfg.units)

    if cfg.size:
        cell_w, cell_h = (mm_to_px(v, dpi) for v in cfg.size)
        fit_cols = math.floor((avail_w + gap) / (cell_w + gap))
        fit_rows = math.floor((avail_h + gap) / (cell_h + gap))
        if fit_cols < 1 or fit_rows < 1:
            raise LayoutError(f"a {fmt(cfg.size[0])} x {fmt(cfg.size[1])} sticker doesn't fit "
                              f"on {cfg.paper} with {fmt(cfg.margin)} margins")
        if cfg.grid is None:
            cols, rows = fit_cols, fit_rows
        else:
            cols, rows = cfg.grid
            if cols > fit_cols or rows > fit_rows:
                raise LayoutError(f"{cols}x{rows} cells of {fmt(cfg.size[0])} x "
                                  f"{fmt(cfg.size[1])} don't fit; at most {fit_cols}x{fit_rows}")
    else:
        if cfg.grid is None:
            raise LayoutError("--grid auto needs --size (e.g. --size 50mm)")
        cols, rows = cfg.grid
        cell_w = (avail_w - (cols - 1) * gap) / cols
        cell_h = (avail_h - (rows - 1) * gap) / rows
        if cell_w < mm_to_px(5, dpi) or cell_h < mm_to_px(5, dpi):
            raise LayoutError(f"{cols}x{rows} leaves cells under 5 mm; use a smaller grid")

    # Centre the block of cells on the page (it only differs with --size).
    block_w = cols * cell_w + (cols - 1) * gap
    block_h = rows * cell_h + (rows - 1) * gap
    return Grid(page_w, page_h, cols, rows, cell_w, cell_h, gap,
                (page_w - block_w) / 2, (page_h - block_h) / 2)


def guide_gap_warning(cfg):
    if cfg.grid_lines != "none" and cfg.gap < MIN_GUIDE_GAP_MM:
        return (f"warning: --gap {format_length(cfg.gap, cfg.units)} is tight for grid guide "
                f"lines; a rough cut may clip outlines (use at least "
                f"{format_length(MIN_GUIDE_GAP_MM, cfg.units)}, or --grid-lines none)")
    return None


def expand_copies(specs, per_page, fill_page):
    """List of specs, one entry per sticker to place, copies expanded.

    With fill_page, cycles through the specs to fill the last page's cells.
    """
    items = [s for s in specs for _ in range(s.copies)]
    if fill_page and items and len(items) % per_page:
        need = per_page - len(items) % per_page
        items += [specs[i % len(specs)] for i in range(need)]
    return items


def paginate(items, per_page):
    return [items[i:i + per_page] for i in range(0, len(items), per_page)]


def describe(grid, cfg):
    fmt = lambda px: format_length(px_to_mm(px, cfg.dpi), cfg.units)
    return (f"{grid.cols}x{grid.rows} grid, cells {fmt(grid.cell_w)} x {fmt(grid.cell_h)}, "
            f"{cfg.paper.upper()}{' landscape' if cfg.landscape else ''} at {cfg.dpi} DPI")
