# stickerkanmi

*"Let's sticker it"*, in Makassar-accented Bahasa.

stickerkanmi lays out a folder of transparent images (PNG/SVG) on printable
sheets and draws a cut-guide outline around each one. It's made for stickers
printed on sticker paper with an ordinary home printer and cut out by hand.

## Install

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

## Usage

```sh
.venv/bin/stickerkanmi <folder> --grid 3x5 --out sheet.jpg
.venv/bin/stickerkanmi --calibrate     # printer check page
.venv/bin/stickerkanmi --help
```

Print at **100% / actual size** with "fit to page" turned off. If you don't,
the stickers won't come out at the sizes you set.
