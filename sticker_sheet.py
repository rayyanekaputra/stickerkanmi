#!/usr/bin/env python3
"""Lay out transparent PNG/SVG images on printable sheets with cut-guide outlines.

Each image's outline is found from its alpha channel, offset outward, smoothed
so it's easy to follow with scissors, and drawn as a thin line. Output is one
high-DPI PNG per page, meant to be printed at 100% / actual size.
"""

import argparse
import io
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

PAPER_MM = {
    "a4": (210, 297),
    "a5": (148, 210),
    "a3": (297, 420),
    "letter": (215.9, 279.4),
}

RASTER_EXTS = {".png", ".webp", ".tif", ".tiff"}
SVG_EXTS = {".svg"}


def mm_to_px(mm, dpi):
    return mm / 25.4 * dpi


def parse_grid(text):
    try:
        cols, rows = (int(n) for n in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"grid must look like 3x5, got {text!r}")
    if cols < 1 or rows < 1:
        raise argparse.ArgumentTypeError("grid needs at least 1x1")
    return cols, rows


def parse_color(text):
    text = text.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError(f"color must be a hex like #b0b0b0, got {text!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def load_rgba(path, svg_px):
    if path.suffix.lower() in SVG_EXTS:
        import cairosvg  # only needed for SVG input

        png = cairosvg.svg2png(url=str(path), output_width=svg_px)
        img = Image.open(io.BytesIO(png))
    else:
        img = Image.open(path)
    return img.convert("RGBA")


def crop_to_content(img, threshold):
    alpha = np.asarray(img.getchannel("A"))
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) == 0:
        return None
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def cut_outline(alpha, threshold, offset_px, smooth_px):
    """Return a single outer polygon around the opaque area of `alpha`.

    Coordinates are in the alpha array's pixel space.
    """
    # A slight blur softens jagged (non-antialiased) source edges before tracing.
    mask = (cv2.GaussianBlur(alpha, (0, 0), 2) > threshold).astype(np.uint8)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pieces = []
    for c in contours:
        if len(c) < 3:
            continue
        # Simplifying first irons out the pixel staircase on diagonal edges.
        poly = Polygon(c.reshape(-1, 2)).simplify(1.5).buffer(0)
        if not poly.is_empty:
            pieces.append(poly)
    shape = unary_union(pieces).buffer(offset_px)

    # Morphological close (grow then shrink) rounds off tight inner notches that
    # scissors can't follow. Keep widening it until separate pieces fuse.
    radius = smooth_px
    for _ in range(4):
        closed = shape.buffer(radius).buffer(-radius)
        if isinstance(closed, Polygon):
            shape = closed
            break
        radius *= 2
    else:
        shape = shape.convex_hull

    if isinstance(shape, MultiPolygon):
        shape = max(shape.geoms, key=lambda g: g.area)
    # Only the outer edge is cut; holes (e.g. inside an "O") stay attached.
    return Polygon(shape.exterior).simplify(0.5)


def render_sticker(img, box_w, box_h, args, dpi):
    """Scale `img` into a box_w x box_h cell. Returns (rgba, outline, warn)."""
    offset_px = mm_to_px(args.offset, dpi)
    line_px = mm_to_px(args.line_width, dpi)
    # Leave room for the offset outline and the line itself inside the cell.
    pad = offset_px + line_px
    avail_w, avail_h = box_w - 2 * pad, box_h - 2 * pad
    if avail_w <= 1 or avail_h <= 1:
        sys.exit("error: cells are too small for that offset; use a smaller grid or offset")

    scale = min(avail_w / img.width, avail_h / img.height)
    w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    warn = scale > 1.0
    img = img.resize((w, h), Image.LANCZOS)

    alpha = np.asarray(img.getchannel("A"))
    # Pad the mask so the offset outline isn't clipped at the image edge.
    p = int(np.ceil(pad)) + 2
    padded = np.pad(alpha, p)
    outline = cut_outline(padded, args.threshold, offset_px, mm_to_px(args.smooth, dpi))
    coords = np.asarray(outline.exterior.coords) - p  # back to image space
    return img, coords, warn


def build_pages(files, args):
    dpi = args.dpi
    paper_w_mm, paper_h_mm = PAPER_MM[args.paper]
    if args.landscape:
        paper_w_mm, paper_h_mm = paper_h_mm, paper_w_mm
    page_w, page_h = round(mm_to_px(paper_w_mm, dpi)), round(mm_to_px(paper_h_mm, dpi))

    cols, rows = args.grid
    margin, gap = mm_to_px(args.margin, dpi), mm_to_px(args.gap, dpi)
    cell_w = (page_w - 2 * margin - (cols - 1) * gap) / cols
    cell_h = (page_h - 2 * margin - (rows - 1) * gap) / rows
    per_page = cols * rows

    # Render SVGs at roughly twice the cell size so downscaling stays sharp.
    svg_px = int(max(cell_w, cell_h) * 2)
    line_px = max(1, round(mm_to_px(args.line_width, dpi) * 16))  # cv2 shift=4 units
    color_bgr = args.line_color[::-1]

    stickers = []
    for path in files:
        img = crop_to_content(load_rgba(path, svg_px), args.threshold)
        if img is None:
            print(f"skip {path.name}: fully transparent", file=sys.stderr)
            continue
        stickers.append((path, img))
    if not stickers:
        sys.exit("error: no usable images found")

    pages = []
    for start in range(0, len(stickers), per_page):
        page = Image.new("RGB", (page_w, page_h), "white")
        outlines = []
        for i, (path, img) in enumerate(stickers[start:start + per_page]):
            r, c = divmod(i, cols)
            cx = margin + c * (cell_w + gap) + cell_w / 2
            cy = margin + r * (cell_h + gap) + cell_h / 2
            art, coords, warn = render_sticker(img, cell_w, cell_h, args, dpi)
            if warn:
                print(f"note {path.name}: upscaled to fit, may print soft "
                      f"(source is smaller than the cell at {dpi} DPI)", file=sys.stderr)
            x0, y0 = round(cx - art.width / 2), round(cy - art.height / 2)
            page.paste(art, (x0, y0), art)
            outlines.append(coords + (x0, y0))

        canvas = np.array(page)[:, :, ::-1].copy()  # RGB -> BGR for cv2
        for coords in outlines:
            pts = np.round(coords * 16).astype(np.int32)  # sub-pixel precision
            cv2.polylines(canvas, [pts], True, color_bgr, thickness=max(1, line_px // 16),
                          lineType=cv2.LINE_AA, shift=4)
        pages.append(Image.fromarray(canvas[:, :, ::-1]))
    return pages


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="folder of transparent PNG/SVG images")
    ap.add_argument("--out", type=Path, default=Path("sheet.png"),
                    help="output file; extra pages get _2, _3... (default: sheet.png)")
    ap.add_argument("--paper", choices=sorted(PAPER_MM), default="a4")
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--grid", type=parse_grid, default=(3, 3), help="COLSxROWS (default: 3x3)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--margin", type=float, default=6, help="page margin in mm (default: 6)")
    ap.add_argument("--gap", type=float, default=4, help="space between cells in mm (default: 4)")
    ap.add_argument("--offset", type=float, default=2.5,
                    help="distance from art to cut line in mm (default: 2.5)")
    ap.add_argument("--smooth", type=float, default=2,
                    help="round off inner notches narrower than this, mm (default: 2)")
    ap.add_argument("--line-width", type=float, default=0.2, help="outline width in mm (default: 0.2)")
    ap.add_argument("--line-color", type=parse_color, default=(170, 170, 170),
                    help="outline hex color (default: #aaaaaa)")
    ap.add_argument("--threshold", type=int, default=10,
                    help="alpha 0-255 above which a pixel counts as art (default: 10)")
    args = ap.parse_args()

    files = sorted(p for p in args.folder.iterdir()
                   if p.suffix.lower() in RASTER_EXTS | SVG_EXTS)
    if not files:
        sys.exit(f"error: no PNG/SVG files in {args.folder}")

    pages = build_pages(files, args)
    for n, page in enumerate(pages, 1):
        out = args.out if n == 1 else args.out.with_stem(f"{args.out.stem}_{n}")
        page.save(out, dpi=(args.dpi, args.dpi))
        print(f"wrote {out}")
    print(f"\nPrint at 100% / 'actual size' — not 'fit to page' — to keep sizes correct.")


if __name__ == "__main__":
    main()
