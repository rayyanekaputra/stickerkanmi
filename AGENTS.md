# Sticker Maker

Lays out a folder of transparent images (PNG/SVG) onto printable sheets and
draws a cut-guide outline around each one, for hand-cutting stickers printed on
a regular home printer.

Current stage: Python CLI package (`sticker_maker/`), phases 0–4 of `PLAN.md`
built. Long-term goal: a compiled desktop app with a GUI (backlog). See
`PLAN.md` for phases and open questions.

## Domain context

- **No cutting machine.** The user prints on an ordinary home inkjet/laser on
  sticker paper and cuts by hand (scissors / craft knife). The "kiss-cut
  outline" is a *printed guide line*, not a vector cut path for a plotter.
  Don't add Cricut/Silhouette/CutContour features unless asked.
- **Output is a raster image, not PDF.** The user saw blurry prints from PDFs
  in their workflow. JPG is the default (quality 95, no chroma subsampling,
  300 DPI, DPI + sRGB profile embedded); PNG is optional. Don't switch to PDF
  output without discussing it.
- **Print at 100% / actual size.** Physical dimensions only hold if the user
  disables "fit to page". Keep reminding them in CLI output and docs.
- **Hand-cutting drives the outline design:** generous offset (~2.5 mm), heavy
  smoothing, one outer contour per sticker (holes are only cut with
  `--holes`, separate pieces get merged), and space between cells.
- **Cut outline stays solid** by default. The user said dashed isn't easier to
  follow (`--line-style` exists but isn't the default).
- **Grid guide lines are on by default:** dashed light-blue lines through the
  middle of the gaps mark each sticker's box for rough-cutting the sheet
  first. They must look clearly different from the solid gray cut outline.
  The user explicitly asked not to drop this.
- Home printers can't print to the edge, so keep a page margin (~5–6 mm).

## How the outline is made (`outline.py`)

1. Alpha channel → slight Gaussian blur → threshold → binary mask.
2. `cv2.findContours` (with holes) → Shapely polygons, simplified; specks
   smaller than ~0.6 mm are dropped.
3. Union, then `buffer(offset)` for the outward offset.
4. Morphological close (`buffer(+r).buffer(-r)`) to fuse separate pieces;
   widen `r` until it's one polygon, convex hull as fallback.
5. **Corridor smoothing** of the exterior ring: repeated Gaussian smoothing,
   with points clamped between `0.8 × offset` from the art and the offset
   shape + `0.66 × smooth`. This straightens shallow wiggles (pixel staircases,
   rows of legs) but keeps deep notches. Then a strong final Gaussian pass
   removes clamp kinks, and the ring is regrown until it clears
   `0.8 × offset` again. Point spacing scales with ring length, so smoothing
   is proportional to sticker size and costs the same at any DPI.
6. With `--holes`, interiors wider than `--hole-min` are smoothed and kept
   clear of the art the same way.

Gotchas found while tuning: plain Gaussian smoothing + regrow leaves wobble
where the shape really steps in and out (bug legs); the corridor alone, run
too long, pulls taut into sharp kinks. The 15-iteration corridor + final
smoothing combination was chosen visually; re-check pixel-art icons and
`tests/fixtures/problems/` after any change.

All geometry is in pixels at the output DPI (outlines are traced on a mask
capped at 1000 px and scaled back); user-facing units are mm or inches.

## Layout

`sticker_maker/`: `units` (length parsing), `config` (`SheetConfig`,
`stickers.toml` overrides), `io` (load/save, ICC→sRGB, SVG via Cairo buffer),
`outline` (pure geometry), `layout` (paper, grid, paging), `render` (sizing,
compositing, lines, preview, calibration page), `cli` (argparse only).
`sticker_sheet.py` is a shim for running from a checkout.

Sizing: cells stretch to fill the page unless `--size` is given; `--grid
auto` needs `--size`. If a traced outline overflows its cell, the art is
shrunk and retraced; in `--sizing uniform` the shrink applies to all stickers
so the shared scale holds.

## Stack

Python 3.14, venv in `.venv/`.

- Pillow: image I/O, compositing, DPI metadata, ImageCms colour conversion
- numpy: arrays
- opencv-python-headless: contour tracing, anti-aliased line drawing
- shapely: offsetting, smoothing, merging outlines
- cairosvg: rasterizing SVG input (needs system Cairo). Rendered via
  `PNGSurface(...).cairo` directly; `svg2png` was 5× slower (PNG encode).
- pytest (dev)

Prefer libraries that will still work when the project is packaged into a
compiled GUI app later (pure-Python or wheels with bundled binaries).

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/sticker-sheet <folder> --grid 3x5 --out sheet.jpg
.venv/bin/sticker-sheet --calibrate                  # printer check page
.venv/bin/sticker-sheet --help                       # ends with 3 examples
.venv/bin/python -m pytest
UPDATE_GOLDEN=1 .venv/bin/python -m pytest -k golden # after an intended visual change
.venv/bin/python tests/fixtures/make_fixtures.py     # regenerate problem images
```

## Working conventions

- **After every finished task, update the context before reporting done.**
  - `AGENTS.md`: new decisions, conventions, gotchas, changed commands or
    file layout. Remove anything that's no longer true.
  - `PLAN.md`: tick completed items, add findings and new to-dos to the
    right phase, update open questions.
  - Keep it concise: record what a future session needs, not a changelog.
- **Commit every update.** After each finished change (code, docs, plan),
  commit it with a clear message; don't leave work uncommitted. Push only
  if asked (there's no remote yet).
- **Stay inside the project directory.** Scratch files, experiments and
  throwaway renders go in `tmp/` here (gitignored), not `/tmp` or anywhere
  else on the system. Full permission inside this directory; never install
  anything system-wide. Packages go only into `.venv/`.
- **Discuss and plan before implementing.** Don't jump to code when the user
  is describing an idea; propose, confirm, then build.
- Verify visually: render a sheet, crop/zoom into outlines, and look at it.
  Most bugs in this project are visual (wobbly lines, clipped outlines,
  wrong spacing) and won't show up in a passing test. Look at the golden
  image before regenerating it.
- Input images live in the project under `assets/<set-name>/` (with the
  source's LICENSE); copy them in before rendering so every sheet is
  reproducible from project files. Rendered sheets go in `test-output/`.
  Currently: `assets/pixelarticons/` (15 icons from pixelarticons 2.4.2, MIT).
- `-h` / `--help` must end with an "Examples" section of 3 runnable
  commands (argparse `epilog`). Keep them working when flags change.
- Millimetres (or inches) in the CLI/UI, pixels internally; convert at the
  boundary (`units.py`). `SheetConfig` stores mm.
- Keep the processing core free of CLI/GUI code so the future GUI can reuse
  it: no `print`/`sys.exit` outside `cli.py`; pass a `log` callable and
  raise `ValueError`/`LayoutError`/`RenderError` instead.
