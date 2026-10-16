"""Sticker Maker: lay out transparent images on printable sheets with cut guides.

The core (outline, layout, render, io) has no CLI code so a GUI can reuse it.
"""

from .config import SheetConfig, StickerSpec, load_specs
from .render import render_calibration, render_pages

__all__ = ["SheetConfig", "StickerSpec", "load_specs", "render_pages", "render_calibration"]
