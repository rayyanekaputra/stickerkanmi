# Sticker Maker

Lays out a folder of transparent images (PNG/SVG) onto printable sheets and
draws a cut-guide outline around each one, for hand-cutting stickers printed on
a regular home printer.

Current stage: Python CLI prototype. Long-term goal: a compiled desktop app
with a GUI. See `PLAN.md` for phases and open questions.

## Domain context

- **No cutting machine.** The user prints on an ordinary home inkjet/laser on
  sticker paper and cuts by hand (scissors / craft knife). The "kiss-cut
  outline" is a *printed guide line*, not a vector cut path for a plotter.
  Don't add Cricut/Silhouette/CutContour features unless asked.
- **Output is a raster image, not PDF.** The user saw blurry prints from PDFs
  in their workflow, so the decision is high-DPI PNG (300 DPI default) with
  DPI metadata embedded. Don't switch to PDF output without discussing it.
- **Print at 100% / actual size.** Physical dimensions only hold if the user
  disables "fit to page". Keep reminding them in CLI output and docs.
- **Hand-cutting drives the outline design:** generous offset (~2.5 mm), heavy
  smoothing of inner notches, one outer contour per sticker (holes are not cut,
  separate pieces get merged), and space between cells.
- **Grid guide lines are on by default:** dashed lines through the middle of
  the gaps mark each sticker's box for rough-cutting the sheet first. They
  must look clearly different from the solid cut outline.
- Home printers can't print to the edge, so keep a page margin (~5–6 mm).

## How the outline is made

1. Alpha channel → slight Gaussian blur → threshold → binary mask.
2. `cv2.findContours` (external only) → Shapely polygons, simplified to remove
   the pixel staircase.
3. Union, then `buffer(offset)` for the outward offset.
4. Morphological close (`buffer(+r).buffer(-r)`) to round off notches and fuse
   separate pieces; widen `r` until it's one polygon, convex hull as fallback.
5. Keep the exterior ring only; draw it anti-aliased with `cv2.polylines`.

All geometry is in pixels at the output DPI; user-facing units are millimetres.

## Stack

Python 3.14, venv in `.venv/`.

- Pillow: image I/O, compositing, DPI metadata
- numpy: arrays
- opencv-python-headless: contour tracing, anti-aliased line drawing
- shapely: offsetting, smoothing, merging outlines
- cairosvg: rasterizing SVG input (needs system Cairo)

Prefer libraries that will still work when the project is packaged into a
compiled GUI app later (pure-Python or wheels with bundled binaries).

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python sticker_sheet.py <folder> --grid 3x5 --out sheet.png
.venv/bin/python sticker_sheet.py --help
```

## Working conventions

- **Discuss and plan before implementing.** Don't jump to code when the user
  is describing an idea; propose, confirm, then build.
- Verify visually: render a sheet, crop/zoom into outlines, and look at it.
  Most bugs in this project are visual (wobbly lines, clipped outlines,
  wrong spacing) and won't show up in a passing test.
- Input images live in the project under `assets/<set-name>/` (with the
  source's LICENSE); copy them in before rendering so every sheet is
  reproducible from project files. Rendered sheets go in `test-output/`.
  Currently: `assets/pixelarticons/` (15 icons from pixelarticons 2.4.2, MIT).
- Millimetres in the CLI/UI, pixels internally; convert at the boundary.
- Keep the processing core free of CLI/GUI code so the future GUI can reuse it.
