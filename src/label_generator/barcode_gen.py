from __future__ import annotations

import io
from functools import lru_cache

import barcode
from barcode.writer import ImageWriter
from PIL import Image


def _calc_check_digit(digits12: str) -> str:
    odds = sum(int(d) for d in digits12[::2])
    evens = sum(int(d) for d in digits12[1::2])
    return str((10 - (odds + evens * 3) % 10) % 10)


def normalize_jan(value: str) -> str:
    """Accept 12-digit (auto-append check) or 13-digit (validate check) JAN code."""
    v = str(value).strip()
    if not v.isdigit():
        raise ValueError(f"JAN must be numeric, got: {v!r}")
    if len(v) == 12:
        return v + _calc_check_digit(v)
    elif len(v) == 13:
        expected = _calc_check_digit(v[:12])
        if v[12] != expected:
            raise ValueError(
                f"JAN check digit wrong for {v!r}: expected {expected}, got {v[12]}"
            )
        return v
    else:
        raise ValueError(f"JAN must be 12 or 13 digits, got {len(v)}: {v!r}")


def jan_display_text(jan13: str) -> str:
    """Return human-readable EAN-13 string: 'X XXXXXX XXXXXX'."""
    return f"{jan13[0]} {jan13[1:7]} {jan13[7:]}"


@lru_cache(maxsize=128)
def render_barcode(jan_raw: str, width: int, height: int) -> Image.Image:
    """Return EAN-13 PNG with digits, resized to (width, height)."""
    jan13 = normalize_jan(jan_raw)
    writer = ImageWriter()
    ean = barcode.get("ean13", jan13, writer=writer)
    options = {
        "module_width": 0.6,
        "module_height": 15.0,
        "quiet_zone": 2.0,
        "font_size": 0,
        "text_distance": 0.0,
        "write_text": False,
        "dpi": 300,
    }
    buf = io.BytesIO()
    ean.write(buf, options=options)
    buf.seek(0)
    native = Image.open(buf).copy()
    return native.resize((width, height), Image.LANCZOS).convert("RGB")
