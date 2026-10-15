# Implementation Plan

Goal: turn a folder of transparent PNG/SVG images into print-ready sticker
sheets with hand-cutting guide outlines, first as a Python CLI, later as a
compiled GUI app.

Each phase ends with something usable. Get the user's sign-off on a phase's
scope before starting it.

---

## Phase 0: Prototype ✅ (done)

Single script `sticker_sheet.py`, proving the core idea.

- Reads PNG/SVG from a folder, crops to visible content
- Fixed grid (`--grid 3x5`) on A3/A4/A5/Letter, portrait or landscape
- Outline: alpha → contour → offset → smooth → anti-aliased line
- Multi-page output, 300 DPI PNG with DPI metadata
- Tested on synthetic shapes only, **not yet on real stickers or a real print**

## Phase 1: Validate with real prints

Before building more, confirm the core is right on paper.

- [ ] Run on the user's real sticker images
- [ ] Print a test sheet at 100% and measure: paper size, margins, offset
- [ ] Tune defaults: offset, line width/color, smoothing, margin for the
      user's printer
- [ ] Add a calibration sheet option (`--calibrate`): ruler marks + a 50 mm
      square to check the printer isn't scaling
- [ ] Collect problem images (thin details, glow/shadow edges, semi-transparent
      areas) as test fixtures

**Exit:** a real printed sheet the user is happy cutting.

## Phase 2: Restructure into a package

Split the script so the GUI can reuse the core later.

```
sticker_maker/
  io.py        load PNG/SVG, crop, save with DPI
  outline.py   mask → contour → offset → smooth (pure geometry)
  layout.py    paper sizes, grid math, cell placement, paging
  render.py    composite art + outlines onto a page
  cli.py       argparse, wraps the above
tests/
  fixtures/    small test images
```

- [ ] Move code into modules, no behaviour change
- [ ] Settings as a dataclass (`SheetConfig`) instead of passing `argparse` args
- [ ] `pyproject.toml` with a `sticker-sheet` console entry point
- [ ] pytest: unit tests for layout math and outline geometry (one polygon,
      no holes, offset distance within tolerance, separate pieces merged)
- [ ] Golden-image test: render a fixture sheet and compare to a stored PNG

**Exit:** same output as phase 0, tested, installable.

## Phase 3: Layout features

"Max out the paper" in more ways than a fixed grid.

- [ ] **Grid guide lines, on by default:** full dashed lines marking each
      sticker's box, so the sheet can be rough-cut into rectangles before
      detail-cutting each outline
  - Drawn through the **center of the gap** between boxes (and around the
    outer edge), so a rough scissor cut never clips a sticker's outline
  - Dashed and visually distinct from the solid cut outline (lighter or a
    different color) so it's clear which line to follow
  - `--grid-lines dashed|corners|none` (default `dashed`); `corners` draws
    crop-mark ticks only
  - Gap must stay wide enough for this; warn if `--gap` gets too small
    (< ~2 mm)
- [ ] `--grid auto --size 50mm`: fit as many N mm stickers as possible
- [ ] Sizing mode: each sticker fills its cell (current) vs. all stickers
      share one scale vs. a fixed physical size
- [ ] Auto-rotate 90° when it lets a sticker print larger in its cell
- [ ] `--copies N` / repeat images to fill a page
- [ ] Optional per-file overrides (e.g. a `stickers.toml` with size/copies)
- [ ] Packed layout (non-grid nesting) as a stretch goal; it fits more
      stickers but is much harder, so only if the grid wastes too much

## Phase 4: Outline & output options

- [ ] Line styles: solid, dashed, dotted
- [ ] Optional white or colored border fill (for colored or clear paper)
- [ ] Optional drop shadow / "sticker look" preview mode
- [ ] Handle semi-transparent edges (glows, shadows) with a sensible threshold
- [ ] Inner cut lines for large holes (opt-in)
- [ ] `--dpi 600` performance check; cap memory on huge source images
- [ ] Colour management: keep sRGB, preserve/convert embedded ICC profiles

## Phase 5: GUI prototype

Still Python, to keep reusing the core.

- [ ] Choose toolkit (see open questions)
- [ ] Drag-and-drop images, live sheet preview, settings panel
- [ ] Per-sticker controls: size, rotation, copies, remove
- [ ] Export PNG, print directly with 100% scaling enforced if the OS allows

## Phase 6: Compiled app

- [ ] Package with PyInstaller or Nuitka for Linux / Windows / macOS
- [ ] Bundle Cairo (or swap cairosvg for `resvg` to avoid the system dependency)
- [ ] Installer, app icon, settings persistence
- [ ] Re-evaluate: if Python packaging is painful, port the core to
      Rust/C++ (the algorithm is small and well-defined by then)

---

## Open questions

1. **Sizing:** should every sticker on a sheet be the same size, or should
   each one grow to fill its cell? (Phase 0 does the latter.)
2. **Units:** millimetres only, or also inches?
3. **Outline look:** solid gray is the default; is a dashed line easier to
   follow when cutting?
4. **SVG fidelity:** is rasterizing SVGs acceptable, or do some need to stay
   vector-sharp at any DPI? (They're rendered at 2× cell size, which should
   be plenty.)
5. **GUI toolkit:** PySide6 (Qt, native-feeling, LGPL) vs. Tauri/web UI vs.
   something lighter like Dear PyGui. Decide in Phase 5.
6. **PDF blur:** the PNG decision rests on PDFs printing blurry. Worth one
   comparison print later; if a correctly embedded PDF prints sharp, PDF
   would make "actual size" printing more reliable.
