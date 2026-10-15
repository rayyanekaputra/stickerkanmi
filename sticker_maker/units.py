"""Physical length units. Everything user-facing is mm or inches; the core
works in pixels at the output DPI. Convert only at these boundaries."""

import re

MM_PER = {"mm": 1.0, "cm": 10.0, "in": 25.4}

_LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|cm|in|\")?\s*$", re.IGNORECASE)


def mm_to_px(mm, dpi):
    return mm / 25.4 * dpi


def px_to_mm(px, dpi):
    return px * 25.4 / dpi


def parse_length(text, default_unit="mm"):
    """'2.5' / '2.5mm' / '0.1in' / '1cm' -> millimetres (float)."""
    if isinstance(text, (int, float)):
        return float(text) * MM_PER[default_unit]
    m = _LENGTH_RE.match(str(text))
    if not m:
        raise ValueError(f"not a length: {text!r} (try 2.5mm or 0.1in)")
    unit = (m.group(2) or default_unit).lower()
    unit = "in" if unit == '"' else unit
    return float(m.group(1)) * MM_PER[unit]


def parse_size(text, default_unit="mm"):
    """'50' / '50mm' / '60x40mm' / '2x1.5in' -> (w_mm, h_mm)."""
    text = str(text).strip().lower()
    m = re.match(r"^([0-9.]+)\s*x\s*([0-9.]+)\s*(mm|cm|in)?$", text)
    if m:
        unit = m.group(3) or default_unit
        return parse_length(m.group(1) + unit), parse_length(m.group(2) + unit)
    side = parse_length(text, default_unit)
    return side, side


def format_length(mm, unit="mm"):
    if unit == "in":
        return f"{mm / 25.4:.2f} in"
    return f"{mm:.1f} mm"
