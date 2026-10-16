"""Image input/output: load PNG/SVG as sRGB RGBA, crop, save pages."""

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

RASTER_EXTS = {".png", ".webp", ".tif", ".tiff"}
SVG_EXTS = {".svg"}
IMAGE_EXTS = RASTER_EXTS | SVG_EXTS
FORMATS = {"jpg": "JPEG", "png": "PNG"}

_SRGB = ImageCms.createProfile("sRGB")
SRGB_ICC = ImageCms.ImageCmsProfile(_SRGB).tobytes()


def find_images(folder):
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)


def load_rgba(path, max_px):
    """Load an image as sRGB RGBA, no larger than ~max_px on its long side.

    Returns (image, natural_scale): image pixels per "natural" pixel (source
    pixels for rasters, CSS px for SVG), so sizes can be compared across files.
    """
    path = Path(path)
    if path.suffix.lower() in SVG_EXTS:
        natural = render_svg(path, 1.0)
        scale = max_px / max(natural.size)
        return render_svg(path, scale), scale

    img = Image.open(path)
    img = to_srgb(img)
    scale = 1.0
    # Cap memory/time on huge sources: nothing above ~max_px is ever printed.
    if max(img.size) > max_px:
        scale = max_px / max(img.size)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.LANCZOS, reducing_gap=3.0)
    return img, scale


def render_svg(path, scale):
    """Rasterize an SVG straight from Cairo's buffer (no PNG round trip)."""
    from cairosvg.parser import Tree  # only needed for SVG input
    from cairosvg.surface import PNGSurface

    surface = PNGSurface(Tree(url=str(path)), None, 96, scale=scale).cairo
    surface.flush()
    # Cairo ARGB32 is premultiplied BGRA in memory on little-endian machines.
    return Image.frombuffer("RGBA", (surface.get_width(), surface.get_height()),
                            bytes(surface.get_data()), "raw", "BGRa", surface.get_stride())


def to_srgb(img):
    """Convert to RGBA in sRGB, honouring an embedded ICC profile."""
    icc = img.info.get("icc_profile")
    if img.mode == "P":
        img = img.convert("RGBA")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            alpha = img.getchannel("A") if "A" in img.getbands() else None
            space = src.profile.xcolor_space.strip()
            base = img.convert({"CMYK": "CMYK", "GRAY": "L"}.get(space, "RGB"))
            base = ImageCms.profileToProfile(base, src, _SRGB, outputMode="RGB")
            if alpha is not None:
                base.putalpha(alpha)
            return base.convert("RGBA")
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass  # unreadable profile: treat the pixels as sRGB
    return img.convert("RGBA")


def crop_to_content(img, threshold):
    alpha = np.asarray(img.getchannel("A"))
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) == 0:
        return None
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def output_format(out, fmt=None):
    """Pick 'jpg' or 'png' from an explicit format or the file extension."""
    if fmt:
        return fmt
    ext = Path(out).suffix.lower().lstrip(".")
    return "jpg" if ext in ("jpg", "jpeg") else "png" if ext == "png" else "jpg"


def page_paths(out, count, fmt):
    """sheet.jpg, sheet_2.jpg, ... with the extension matching the format."""
    out = Path(out)
    if out.suffix.lower().lstrip(".") not in ("jpg", "jpeg", "png"):
        out = out.with_name(out.name + "." + fmt)
    elif output_format(out) != fmt:
        out = out.with_suffix("." + fmt)
    return [out if n == 1 else out.with_stem(f"{out.stem}_{n}") for n in range(1, count + 1)]


def save_page(img, path, fmt, dpi):
    """Save an RGB page with DPI and an sRGB profile embedded."""
    opts = {"dpi": (dpi, dpi), "icc_profile": SRGB_ICC}
    if fmt == "jpg":
        # High quality and no chroma subsampling keep thin coloured lines crisp.
        opts.update(quality=95, subsampling=0)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, FORMATS[fmt], **opts)
