# stickerkanmi

*"let's sticker it"*, in bahasa (makassar accent).

if youre too lazy to layout you stickers evenly-spaced or to maximize your
paper efficiency. stickerkanmi is your go to choice

## install

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

## usage
simply point it at a folder of your stickers (png, svg). it'll detect every sticker in that folder then render them in papers, dynamically ofcourse based on your settings.

```sh
.venv/bin/stickerkanmi <folder> --grid 3x5 --out sheet.jpg
.venv/bin/stickerkanmi --calibrate     # printer check page
.venv/bin/stickerkanmi --help
```

print at **100% / actual size** with "fit to page" turned off. if you don't,
the stickers won't come out at the sizes you set.
