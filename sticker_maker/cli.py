"""Command line: argparse -> SheetConfig -> pages on disk."""

import argparse
import sys
from pathlib import Path

from . import io as sio
from .config import OVERRIDES_FILE, SheetConfig, load_specs
from .layout import PAPER_MM, LayoutError, describe, guide_gap_warning
from .render import RenderError, render_calibration, render_pages
from .units import parse_length, parse_size

DESCRIPTION = """\
Lay out transparent PNG/SVG images on printable sheets with cut-guide outlines.

Each image's outline is found from its alpha channel, offset outward, smoothed
so it's easy to follow with scissors, and drawn as a thin line. Dashed grid
lines mark each sticker's box for rough-cutting the sheet first. Output is one
high-DPI JPG (or PNG) per page, meant to be printed at 100% / actual size.

Lengths accept units: 2.5, 2.5mm, 0.1in, 1cm. Plain numbers use --units.
Per-file settings (copies, size, rotate, skip) go in <folder>/{toml}.
""".format(toml=OVERRIDES_FILE)

EXAMPLES = """\
examples:
  # 3x5 stickers on A4, one JPG per page
  sticker-sheet assets/pixelarticons --grid 3x5 --out sheet.jpg

  # as many 40 mm stickers as fit, 2 copies of each, last page filled up
  sticker-sheet my-stickers --grid auto --size 40mm --copies 2 --fill-page

  # US Letter in inches, all stickers at one shared scale, wider cut margin
  sticker-sheet my-stickers --paper letter --units in --sizing uniform --offset 0.12in
"""


def _grid(text):
    if text.lower() == "auto":
        return None
    try:
        cols, rows = (int(n) for n in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"grid must look like 3x5 or 'auto', got {text!r}")
    if cols < 1 or rows < 1:
        raise argparse.ArgumentTypeError("grid needs at least 1x1")
    return cols, rows


def _color_or_none(text):
    return None if text.lower() == "none" else _color(text)


def _color(text):
    t = text.lstrip("#")
    if len(t) != 6:
        raise argparse.ArgumentTypeError(f"color must be a hex like #b0b0b0, got {text!r}")
    try:
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise argparse.ArgumentTypeError(f"color must be a hex like #b0b0b0, got {text!r}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="sticker-sheet", description=DESCRIPTION, epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, nargs="?", help="folder of transparent PNG/SVG images")
    ap.add_argument("--out", type=Path, default=Path("sheet.jpg"),
                    help="output file; extra pages get _2, _3... (default: sheet.jpg)")
    ap.add_argument("--format", choices=["jpg", "png"],
                    help="output format (default: from --out's extension, else jpg)")
    ap.add_argument("--units", choices=["mm", "in"], default="mm",
                    help="unit for plain numbers and messages (default: mm)")
    ap.add_argument("--calibrate", action="store_true",
                    help="write a printer calibration page (rulers + 50 mm square) instead")

    g = ap.add_argument_group("page")
    g.add_argument("--paper", choices=sorted(PAPER_MM), default="a4")
    g.add_argument("--landscape", action="store_true")
    g.add_argument("--dpi", type=int, default=300)
    g.add_argument("--margin", default="6mm", help="page margin (default: 6mm)")

    g = ap.add_argument_group("layout")
    g.add_argument("--grid", type=_grid, default=(3, 3),
                   help="COLSxROWS, or 'auto' to fit as many --size cells as possible "
                        "(default: 3x3)")
    g.add_argument("--size", help="sticker (cell) size, e.g. 50mm, 2in or 60x40mm; "
                                  "without it cells stretch to fill the page")
    g.add_argument("--gap", default="4mm", help="space between cells (default: 4mm)")
    g.add_argument("--sizing", choices=["fill", "uniform"], default="fill",
                   help="fill: each sticker grows to fill its cell; uniform: all share one "
                        "scale so relative sizes are kept (default: fill)")
    g.add_argument("--rotate", choices=["auto", "never"], default="auto",
                   help="turn stickers 90° when that prints them larger (default: auto)")
    g.add_argument("--copies", type=int, default=1, help="copies of each image (default: 1)")
    g.add_argument("--fill-page", action="store_true",
                   help="repeat stickers to fill the empty cells on the last page")
    g.add_argument("--grid-lines", choices=["dashed", "corners", "none"], default="dashed",
                   help="rough-cut guides through the gaps (default: dashed)")
    g.add_argument("--grid-line-color", type=_color, default="#78aadc",
                   help="guide line hex color (default: #78aadc)")

    g = ap.add_argument_group("cut outline")
    g.add_argument("--offset", default="2.5mm", help="distance from art to cut line (default: 2.5mm)")
    g.add_argument("--smooth", default="3mm",
                   help="how much the line is smoothed; notches narrower than about twice "
                        "this are rounded off (default: 3mm)")
    g.add_argument("--line-width", default="0.2mm", help="outline width (default: 0.2mm)")
    g.add_argument("--line-color", type=_color, default="#aaaaaa",
                   help="outline hex color (default: #aaaaaa)")
    g.add_argument("--line-style", choices=["solid", "dashed", "dotted"], default="solid")
    g.add_argument("--holes", action="store_true",
                   help="also draw cut lines inside large holes (e.g. a donut's middle)")
    g.add_argument("--hole-min", default="12mm",
                   help="with --holes, skip holes narrower than this (default: 12mm)")
    g.add_argument("--fill-color", type=_color_or_none, default=None,
                   help="fill inside the outline with this color, for colored or clear "
                        "paper (e.g. #ffffff; default: none)")
    g.add_argument("--threshold", type=int, default=10,
                   help="alpha 0-255 above which a pixel counts as art (default: 10)")

    g = ap.add_argument_group("output")
    g.add_argument("--preview", action="store_true",
                   help="also write a '_preview' mock-up of the cut stickers (not for printing)")
    return ap


def config_from_args(args):
    u = args.units
    length = lambda v: parse_length(v, u)
    try:
        return SheetConfig(
            paper=args.paper, landscape=args.landscape, dpi=args.dpi, margin=length(args.margin),
            grid=args.grid, size=parse_size(args.size, u) if args.size else None,
            gap=length(args.gap), sizing=args.sizing, rotate=args.rotate,
            copies=args.copies, fill_page=args.fill_page,
            offset=length(args.offset), smooth=length(args.smooth),
            line_width=length(args.line_width), line_color=args.line_color,
            line_style=args.line_style, threshold=args.threshold,
            holes=args.holes, hole_min=length(args.hole_min), fill_color=args.fill_color,
            grid_lines=args.grid_lines,
            grid_line_color=args.grid_line_color,
            units=u)
    except ValueError as e:
        sys.exit(f"error: {e}")


def _log(msg):
    print(msg, file=sys.stderr)


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    cfg = config_from_args(args)
    fmt = sio.output_format(args.out, args.format)

    if args.calibrate:
        out = sio.page_paths(args.out.with_stem(args.out.stem + "_calibration"), 1, fmt)[0]
        sio.save_page(render_calibration(cfg), out, fmt, cfg.dpi)
        print(f"wrote {out}")
        print("\nPrint at 100% / 'actual size' (not 'fit to page'), then measure the squares.")
        return

    if args.folder is None:
        ap.error("a folder of images is required (or use --calibrate)")
    if not args.folder.is_dir():
        sys.exit(f"error: {args.folder} is not a folder")
    files = sio.find_images(args.folder)
    if not files:
        sys.exit(f"error: no PNG/SVG files in {args.folder}")
    if warning := guide_gap_warning(cfg):
        _log(warning)

    try:
        specs = load_specs(files, args.folder, cfg, log=_log)
        pages, grid = render_pages(specs, cfg, log=_log)
        print(describe(grid, cfg))
        for out, page in zip(sio.page_paths(args.out, len(pages), fmt), pages):
            sio.save_page(page, out, fmt, cfg.dpi)
            print(f"wrote {out}")
        if args.preview:
            cfg.preview = True
            previews, _ = render_pages(specs, cfg, log=lambda m: None)
            stem_out = args.out.with_stem(args.out.stem + "_preview")
            for out, page in zip(sio.page_paths(stem_out, len(previews), fmt), previews):
                sio.save_page(page, out, fmt, cfg.dpi)
                print(f"wrote {out} (preview, not for printing)")
    except (LayoutError, RenderError, ValueError) as e:
        sys.exit(f"error: {e}")
    print("\nPrint at 100% / 'actual size' (not 'fit to page') to keep sizes correct.")


if __name__ == "__main__":
    main()
