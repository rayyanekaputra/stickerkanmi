"""Sheet settings and per-sticker overrides. All lengths are millimetres."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .units import parse_length

OVERRIDES_FILE = "stickers.toml"


@dataclass
class SheetConfig:
    # Page
    paper: str = "a4"
    landscape: bool = False
    dpi: int = 300
    margin: float = 6.0
    # Layout
    grid: tuple[int, int] | None = (3, 3)  # None = auto: as many `size` cells as fit
    size: tuple[float, float] | None = None  # cell (finished sticker) size; None = stretch
    gap: float = 4.0
    sizing: str = "fill"  # fill: each sticker fills its cell; uniform: one shared scale
    rotate: str = "auto"  # auto: turn 90° when that prints larger; never
    copies: int = 1
    fill_page: bool = False  # repeat stickers to fill the last page
    # Cut outline
    offset: float = 2.5
    smooth: float = 3.0
    line_width: float = 0.2
    line_color: tuple[int, int, int] = (170, 170, 170)
    line_style: str = "solid"  # solid | dashed | dotted
    threshold: int = 10
    holes: bool = False  # also cut large holes (inner outlines)
    hole_min: float = 12.0  # only holes at least this wide get a cut line
    fill_color: tuple[int, int, int] | None = None  # border fill inside the outline
    # Grid guide lines (rough-cut boxes)
    grid_lines: str = "dashed"  # dashed | corners | none
    grid_line_color: tuple[int, int, int] = (120, 170, 220)
    grid_line_width: float = 0.15
    # Output
    preview: bool = False  # "sticker look" mock-up instead of a print sheet
    units: str = "mm"  # for messages


@dataclass
class StickerSpec:
    path: Path
    copies: int = 1
    size: float | None = None  # mm, longest side of the cut sticker
    rotate: str | None = None  # None = sheet default; "auto" | "0" | "90"
    skip: bool = False


def load_specs(files, folder, config, log=print):
    """One StickerSpec per file, with stickers.toml overrides applied.

    Raises ValueError for a broken stickers.toml.
    """
    overrides = {}
    toml_path = Path(folder) / OVERRIDES_FILE if folder else None
    if toml_path and toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                overrides = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{OVERRIDES_FILE}: {e}")
    names = {p.name for p in files}
    for name in overrides:
        if name not in names:
            log(f"warning: {OVERRIDES_FILE}: no image named {name!r}")

    specs = []
    for path in files:
        spec = StickerSpec(path, copies=config.copies)
        for key, value in overrides.get(path.name, {}).items():
            if key == "copies":
                spec.copies = int(value)
            elif key == "size":
                spec.size = parse_length(value, config.units)
            elif key == "rotate":
                spec.rotate = str(value).lower()
                if spec.rotate not in ("auto", "0", "90"):
                    raise ValueError(f"{OVERRIDES_FILE}: {path.name}: rotate must be 0, 90 or "
                                     f"\"auto\"")
            elif key == "skip":
                spec.skip = bool(value)
            else:
                log(f"warning: {OVERRIDES_FILE}: {path.name}: unknown setting {key!r}")
        if not spec.skip and spec.copies > 0:
            specs.append(spec)
    return specs
