"""Composite art, cut outlines and grid guide lines onto pages."""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely import affinity

from . import io as sio
from .layout import expand_copies, make_grid, paginate, page_size_px
from .outline import cut_outline
from .units import mm_to_px

SHIFT = 4  # cv2 sub-pixel bits: coordinates are drawn in 1/16 px
DASH_MM = {"dashed": (2.0, 1.2), "dotted": (0.05, 0.8)}
GUIDE_DASH_MM = (3.0, 2.0)
CORNER_TICK_MM = 2.5
OUTLINE_MAX_PX = 1000
PREVIEW_BG = (222, 218, 210)


class RenderError(ValueError):
    pass


@dataclass
class Sticker:
    """A source image, cropped, at roughly 2x the size it will print."""
    spec: object
    img: Image.Image
    natural_scale: float  # img px per natural (source / CSS) px


@dataclass
class Placed:
    art: Image.Image  # final-size RGBA, already rotated
    outline: object  # shapely Polygon in art pixel space
    note: str | None = None
    shrunk: float = 1.0  # < 1 when the outline overflowed and the art was shrunk


def load_stickers(specs, grid, cfg, log=print):
    max_px = int(max(grid.cell_w, grid.cell_h) * 2)
    stickers = []
    for spec in specs:
        img, natural = sio.load_rgba(spec.path, max_px)
        img = sio.crop_to_content(img, cfg.threshold)
        if img is None:
            log(f"skip {spec.path.name}: fully transparent")
            continue
        stickers.append(Sticker(spec, img, natural))
    return stickers


def _pad_px(cfg):
    """Room the cut line needs outside the art."""
    return mm_to_px(cfg.offset + cfg.line_width, cfg.dpi)


def _fit(w, h, box_w, box_h):
    return min(box_w / w, box_h / h)


def choose_rotation(sticker, box_w, box_h, cfg):
    """0 or 90: turn the art when that lets it print noticeably larger."""
    mode = sticker.spec.rotate or cfg.rotate
    if mode in ("0", "never"):
        return 0
    if mode == "90":
        return 90
    w, h = sticker.img.size
    return 90 if _fit(h, w, box_w, box_h) > _fit(w, h, box_w, box_h) * 1.03 else 0


def plan_scales(stickers, grid, cfg, log=print):
    """Scale (output px per img px) and rotation for each sticker."""
    pad = _pad_px(cfg)
    box_w, box_h = grid.cell_w - 2 * pad, grid.cell_h - 2 * pad
    if box_w <= 1 or box_h <= 1:
        raise RenderError("cells are too small for that offset; use a smaller grid or offset")
    plans = {}
    for s in stickers:
        rot = choose_rotation(s, box_w, box_h, cfg)
        w, h = s.img.size if rot == 0 else s.img.size[::-1]
        plans[id(s)] = [_fit(w, h, box_w, box_h), rot]

    if cfg.sizing == "uniform":
        # One physical scale per natural pixel: relative sizes are kept and the
        # biggest sticker sets it.
        k = min(scale * s.natural_scale for s in stickers for scale in [plans[id(s)][0]])
        for s in stickers:
            plans[id(s)][0] = k / s.natural_scale

    for s in stickers:
        if s.spec.size:  # per-file size override: longest side of the cut sticker
            art_px = mm_to_px(s.spec.size, cfg.dpi) - 2 * pad
            want = art_px / max(s.img.size)
            if want > plans[id(s)][0] * 1.001:
                log(f"note {s.spec.path.name}: size {s.spec.size:g} mm is bigger than its "
                    f"cell; using the cell size")
            else:
                plans[id(s)][0] = max(want, 1 / max(s.img.size))
    return {k: tuple(v) for k, v in plans.items()}


def trace(alpha_img, cfg, offset_px, hole_min):
    """Cut line for an alpha channel, in its pixel space.

    Traced on a mask of at most OUTLINE_MAX_PX: the line is smooth, so tracing
    a 600 DPI sticker at full size costs time without changing the result.
    """
    f = min(1.0, OUTLINE_MAX_PX / max(alpha_img.size))
    if f < 1.0:
        alpha_img = alpha_img.resize((max(1, round(alpha_img.width * f)),
                                      max(1, round(alpha_img.height * f))), Image.BOX)
    smooth = mm_to_px(cfg.smooth, cfg.dpi) * f
    # Pad the mask so the outline isn't clipped at the image edge; smoothing
    # may push it a bit past the plain offset.
    p = int(np.ceil(offset_px * f + smooth)) + 4
    outline = cut_outline(np.pad(np.asarray(alpha_img), p), cfg.threshold, offset_px * f,
                          smooth, min_piece_px=mm_to_px(0.6, cfg.dpi) * f,
                          hole_min_px=hole_min * f if hole_min else None)
    outline = affinity.translate(outline, -p, -p)
    return affinity.scale(outline, 1 / f, 1 / f, origin=(0, 0)) if f < 1.0 else outline


def place_sticker(sticker, scale, rot, grid, cfg):
    """Resize/rotate the art and trace its cut line, shrinking if it overflows."""
    dpi = cfg.dpi
    offset_px = mm_to_px(cfg.offset, dpi)
    hole_min = mm_to_px(cfg.hole_min, dpi) if cfg.holes else None
    line_px = mm_to_px(cfg.line_width, dpi)
    planned = scale
    for _ in range(4):
        w = max(1, round(sticker.img.width * scale))
        h = max(1, round(sticker.img.height * scale))
        art = sticker.img.resize((w, h), Image.LANCZOS)
        if rot == 90:
            art = art.transpose(Image.Transpose.ROTATE_90)
        outline = trace(art.getchannel("A"), cfg, offset_px, hole_min)
        minx, miny, maxx, maxy = outline.bounds
        ow, oh = maxx - minx + line_px, maxy - miny + line_px
        over = max(ow / grid.cell_w, oh / grid.cell_h)
        if over <= 1.0:
            break
        scale /= over * 1.01
    note = None
    if scale * sticker.natural_scale > 1.0 and sticker.spec.path.suffix.lower() != ".svg":
        note = (f"note {sticker.spec.path.name}: upscaled to fit, may print soft "
                f"(source is smaller than its cell at {dpi} DPI)")
    return Placed(art, outline, note, scale / planned)


def _outline_center_offset(placed):
    """Where to put the art so the outline (not the art) is centred."""
    minx, miny, maxx, maxy = placed.outline.bounds
    return (minx + maxx) / 2, (miny + maxy) / 2


# --- drawing ---------------------------------------------------------------

def _to_fixed(coords):
    return np.round(np.asarray(coords) * (1 << SHIFT)).astype(np.int32)


def dash_runs(coords, dash, gap, phase=0.0, closed=False):
    """Split a polyline into dash runs by arc length.

    `phase` is the pattern position at the first point, so collinear segments
    drawn with phase = their absolute start coordinate line up exactly.
    """
    pts = np.asarray(coords, dtype=float)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    period = dash + gap
    if total == 0 or period <= 0:
        return []
    start = -(phase % period)
    runs = []
    while start < total:
        a, b = max(start, 0.0), min(start + dash, total)
        if b > a:
            ts = np.concatenate([[a], cum[(cum > a) & (cum < b)], [b]])
            runs.append(np.column_stack([np.interp(ts, cum, pts[:, 0]),
                                         np.interp(ts, cum, pts[:, 1])]))
        start += period
    return runs


def draw_line(canvas, coords, color, width_px, style="solid", dpi=300, closed=True, phase=0.0):
    thickness = max(1, round(width_px))
    if style == "solid":
        cv2.polylines(canvas, [_to_fixed(coords)], closed, color, thickness, cv2.LINE_AA, SHIFT)
        return
    dash, gap = (mm_to_px(v, dpi) for v in DASH_MM.get(style, GUIDE_DASH_MM))
    if style == "dotted":
        dash = max(dash, 0.5)
    runs = dash_runs(coords, dash, gap, phase, closed)
    cv2.polylines(canvas, [_to_fixed(r) for r in runs], False, color, thickness,
                  cv2.LINE_AA, SHIFT)


def draw_grid_lines(canvas, grid, count, cfg):
    """Rough-cut boxes through the middle of the gaps around each used cell."""
    if cfg.grid_lines == "none":
        return
    dpi = cfg.dpi
    color = cfg.grid_line_color[::-1]
    width = mm_to_px(cfg.grid_line_width, dpi)
    if cfg.grid_lines == "corners":
        arm = mm_to_px(CORNER_TICK_MM, dpi) / 2
        for i in range(count):
            x, y, w, h = grid.guide_box(i)
            for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                draw_line(canvas, [(cx - arm, cy), (cx + arm, cy)], color, width, closed=False)
                draw_line(canvas, [(cx, cy - arm), (cx, cy + arm)], color, width, closed=False)
        return
    dash, gap = (mm_to_px(v, dpi) for v in GUIDE_DASH_MM)
    for i in range(count):
        x, y, w, h = grid.guide_box(i)
        # Phase anchored to page coordinates: shared edges of neighbouring
        # boxes draw the exact same dashes.
        for p0, p1, phase in (((x, y), (x + w, y), x), ((x, y + h), (x + w, y + h), x),
                              ((x, y), (x, y + h), y), ((x + w, y), (x + w, y + h), y)):
            runs = dash_runs([p0, p1], dash, gap, phase)
            cv2.polylines(canvas, [_to_fixed(r) for r in runs], False, color,
                          max(1, round(width)), cv2.LINE_AA, SHIFT)


def _fill_polygon(canvas, polygon, color, bg):
    cv2.fillPoly(canvas, [_to_fixed(polygon.exterior.coords)], color, cv2.LINE_AA, SHIFT)
    for ring in polygon.interiors:
        cv2.fillPoly(canvas, [_to_fixed(ring.coords)], bg, cv2.LINE_AA, SHIFT)


def _shadow(canvas, polygons, dpi):
    """Soft drop shadow under each sticker for the preview."""
    mask = np.zeros(canvas.shape[:2], np.uint8)
    d = mm_to_px(0.8, dpi)
    for poly in polygons:
        cv2.fillPoly(mask, [_to_fixed(affinity.translate(poly, d, d * 1.5).exterior.coords)],
                     255, cv2.LINE_AA, SHIFT)
    mask = cv2.GaussianBlur(mask, (0, 0), mm_to_px(1.2, dpi)).astype(np.float32) / 255 * 0.35
    canvas[:] = (canvas * (1 - mask[..., None])).astype(np.uint8)


def render_pages(specs, cfg, log=print):
    """Lay out `specs` (StickerSpecs) and return a list of RGB page images."""
    grid = make_grid(cfg)
    stickers = load_stickers(specs, grid, cfg, log)
    if not stickers:
        raise RenderError("no usable images found")
    plans = plan_scales(stickers, grid, cfg, log)
    by_spec = {id(s.spec): s for s in stickers}
    items = [by_spec[id(sp)] for sp in expand_copies([s.spec for s in stickers],
                                                     grid.per_page, cfg.fill_page)]

    cache = {id(s): place_sticker(s, *plans[id(s)], grid, cfg) for s in stickers}
    if cfg.sizing == "uniform":
        # Keep the shared scale: if one sticker had to shrink, shrink them all.
        k = min(pl.shrunk for pl in cache.values())
        for s in stickers:
            if cache[id(s)].shrunk > k * 1.001:
                scale, rot = plans[id(s)]
                cache[id(s)] = place_sticker(s, scale * k, rot, grid, cfg)
    noted = set()
    bg = PREVIEW_BG if cfg.preview else (255, 255, 255)
    pages = []
    for page_items in paginate(items, grid.per_page):
        placed = []
        for i, st in enumerate(page_items):
            pl = cache[id(st)]
            if pl.note and id(st) not in noted:
                noted.add(id(st))
                log(pl.note)
            x, y, w, h = grid.cell(i)
            ox, oy = _outline_center_offset(pl)
            x0, y0 = round(x + w / 2 - ox), round(y + h / 2 - oy)
            placed.append((pl, (x0, y0), affinity.translate(pl.outline, x0, y0)))
        pages.append(_compose(grid, placed, cfg, bg))
    return pages, grid


def _compose(grid, placed, cfg, bg):
    dpi = cfg.dpi
    canvas = np.full((grid.page_h, grid.page_w, 3), bg[::-1], np.uint8)  # BGR
    outlines = [poly for _, _, poly in placed]
    if cfg.preview:
        _shadow(canvas, outlines, dpi)
        for poly in outlines:
            _fill_polygon(canvas, poly, (255, 255, 255), bg[::-1])
    else:
        draw_grid_lines(canvas, grid, len(placed), cfg)
        if cfg.fill_color:
            for poly in outlines:
                _fill_polygon(canvas, poly, cfg.fill_color[::-1], bg[::-1])

    page = Image.fromarray(canvas[:, :, ::-1])
    for pl, pos, _ in placed:
        page.paste(pl.art, pos, pl.art)
    if cfg.preview:
        return page

    canvas = np.array(page)[:, :, ::-1].copy()
    color = cfg.line_color[::-1]
    width = mm_to_px(cfg.line_width, dpi)
    for poly in outlines:
        for ring in [poly.exterior, *poly.interiors]:
            draw_line(canvas, np.asarray(ring.coords)[:-1], color, width, cfg.line_style, dpi)
    return Image.fromarray(canvas[:, :, ::-1])


# --- calibration -------------------------------------------------------------

def _font(px):
    try:
        return ImageFont.load_default(size=px)
    except (TypeError, OSError):
        return ImageFont.load_default()


def render_calibration(cfg):
    """A page with rulers and reference squares to check the printer's scaling."""
    dpi = cfg.dpi
    W, H = page_size_px(cfg)
    px = lambda mm: mm_to_px(mm, dpi)
    m = px(cfg.margin)
    ink, faint = (0, 0, 0), (150, 150, 150)
    line = max(1, round(px(0.2)))
    small, mid, big = _font(round(px(2.2))), _font(round(px(3))), _font(round(px(4.5)))

    # Printable-area frame at the margin: if it's cut off, the margin is too small.
    canvas = np.full((H, W, 3), 255, np.uint8)
    draw_line(canvas, [(m, m), (W - m, m), (W - m, H - m), (m, H - m)], (180, 140, 90),
              px(0.2), "dashed", dpi)
    page = Image.fromarray(canvas[:, :, ::-1])
    d = ImageDraw.Draw(page)

    # Millimetre rulers along the top and left, starting at the margin.
    start = m + px(4)
    length_x = (W - 2 * m - px(8)) / px(1)
    length_y = (H - 2 * m - px(25)) / px(1)  # stop above the inch ruler
    for i in range(int(length_x) + 1):
        x = start + px(i)
        tick = px(5) if i % 10 == 0 else px(3.5) if i % 5 == 0 else px(2)
        d.line([(x, start), (x, start + tick)], ink, line)
        if i % 10 == 0:
            d.text((x + px(0.6), start + px(3.6)), str(i // 10), ink, small)
    for i in range(int(length_y) + 1):
        y = start + px(i)
        tick = px(5) if i % 10 == 0 else px(3.5) if i % 5 == 0 else px(2)
        d.line([(start, y), (start + tick, y)], ink, line)
        if i % 10 == 0 and i:
            d.text((start + px(3.6), y + px(0.4)), str(i // 10), ink, small)
    d.text((start + px(8), start + px(8)), "cm", ink, small)

    # Inch ruler along the bottom, 1/8" ticks.
    inch_y = H - m - px(4)
    for i in range(int((W - 2 * m - px(8)) / px(25.4 / 8)) + 1):
        x = start + px(i * 25.4 / 8)
        tick = px(5) if i % 8 == 0 else px(3.5) if i % 4 == 0 else px(2.5) if i % 2 == 0 else px(1.5)
        d.line([(x, inch_y), (x, inch_y - tick)], ink, line)
        if i % 8 == 0:
            d.text((x + px(0.6), inch_y - px(8)), f'{i // 8}"', ink, small)

    # Reference squares.
    sq_x, sq_y = start + px(20), start + px(30)
    d.rectangle([sq_x, sq_y, sq_x + px(50), sq_y + px(50)], outline=ink, width=line)
    d.text((sq_x, sq_y + px(52)), "50 mm", ink, mid)
    sq2_x = sq_x + px(65)
    d.rectangle([sq2_x, sq_y, sq2_x + px(50.8), sq_y + px(50.8)], outline=ink, width=line)
    d.text((sq2_x, sq_y + px(52.8)), "2 in (50.8 mm)", ink, mid)

    text_y = sq_y + px(68)
    lines = [
        ("Printer calibration", big, ink),
        (f"{cfg.paper.upper()}{' landscape' if cfg.landscape else ''}, {dpi} DPI, "
         f"{cfg.margin:g} mm margin", mid, faint),
        ("", mid, ink),
        ("1. Print at 100% / 'actual size' (turn OFF 'fit to page').", mid, ink),
        ("2. Measure the squares with a ruler: 50 mm and 2 in exactly.", mid, ink),
        ("   Bigger or smaller means the printer is scaling the page.", mid, ink),
        ("3. Check the cm and inch rulers against a real ruler.", mid, ink),
        ("4. The dashed frame marks the page margin. If any part of it is", mid, ink),
        ("   missing, the printer can't reach that far: raise --margin.", mid, ink),
    ]
    for text, font, color in lines:
        d.text((sq_x, text_y), text, color, font)
        text_y += px(4.6) if font is mid else px(7)
    return page
