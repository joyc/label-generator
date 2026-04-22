from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')


def safe_filename(name: str) -> str:
    return _ILLEGAL_CHARS.sub("_", name)


def _measure_text(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _wrap_text(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> list[str]:
    """Break into at most 2 lines (CJK per-char), truncate overflow with …."""
    if _measure_text(font, text) <= max_width:
        return [text]

    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if _measure_text(font, candidate) > max_width:
            if current:
                lines.append(current)
                if len(lines) == 2:
                    last = lines[-1]
                    while last and _measure_text(font, last + "…") > max_width:
                        last = last[:-1]
                    lines[-1] = last + "…"
                    return lines
                current = ch
            else:
                lines.append(ch)
                current = ""
        else:
            current = candidate

    if current:
        lines.append(current)
    return lines[:2]


class LabelRenderer:
    def __init__(
        self,
        template_path: str | Path,
        layout: dict[str, Any],
        font_path: str | Path,
        bold_font_path: str | Path | None = None,
    ):
        tp = Path(template_path)
        if not tp.exists():
            raise FileNotFoundError(f"Template not found: {tp.resolve()}")
        fp = Path(font_path)
        if not fp.exists():
            raise FileNotFoundError(f"Font not found: {fp.resolve()}")

        self._template = Image.open(tp).convert("RGBA")
        self._layout = layout
        self._font_path = str(fp)

        bp = Path(bold_font_path) if bold_font_path else None
        self._bold_font_path = str(bp) if bp and bp.exists() else str(fp)

    @lru_cache(maxsize=32)
    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self._font_path, size)

    @lru_cache(maxsize=32)
    def _bold_font(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self._bold_font_path, size)

    def render(self, record: dict[str, Any]) -> Image.Image:
        img = self._template.copy()
        draw = ImageDraw.Draw(img)

        for field, spec in self._layout.items():
            if field.startswith("_"):
                continue
            value = str(record.get(field, "")).strip()
            if not value:
                continue

            kind = spec.get("type", "text")
            xy = tuple(spec["xy"])

            if kind == "text":
                self._draw_text(draw, value, spec, xy)
            elif kind == "barcode":
                self._paste_barcode(img, value, spec, xy)

        return img.convert("RGB")

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        value: str,
        spec: dict,
        xy: tuple,
    ) -> None:
        use_bold = spec.get("bold", False)
        font = (
            self._bold_font(spec.get("font_size", 24))
            if use_bold
            else self._font(spec.get("font_size", 24))
        )
        color = spec.get("color", "#000000")
        anchor = spec.get("anchor", "lt")
        max_width = spec.get("max_width")

        if max_width:
            lines = _wrap_text(font, value, max_width)
        else:
            lines = [value]

        line_height = font.getbbox("Ag")[3] + 4
        x, y = xy

        for line in lines:
            draw.text((x, y), line, font=font, fill=color, anchor=anchor)
            y += line_height

    def _paste_barcode(
        self,
        img: Image.Image,
        value: str,
        spec: dict,
        xy: tuple,
    ) -> None:
        from .barcode_gen import normalize_jan, render_barcode

        width = spec.get("width", 300)
        height = spec.get("height", 80)
        rotation = spec.get("rotation", 0)
        anchor = spec.get("anchor", "lt")

        show_text = spec.get("show_text", True)

        try:
            jan13 = normalize_jan(value)
            bars = render_barcode(value, width, height)
        except ValueError as e:
            print(f"  [barcode] skip — {e}")
            return

        if show_text:
            font_size = max(8, height // 10)
            font = self._font(font_size)
            text_h = font.getbbox("0")[3] + 4
            bc_img = Image.new("RGB", (width, height + text_h), "white")
            bc_img.paste(bars, (0, 0))
            draw = ImageDraw.Draw(bc_img)
            digits = jan13  # 13 chars, evenly spaced left-to-right
            step = width / (len(digits) - 1)
            for i, ch in enumerate(digits):
                x = round(i * step)
                if i == 0:
                    a = "lt"
                elif i == len(digits) - 1:
                    a = "rt"
                else:
                    a = "mt"
                draw.text((x, height + 2), ch, font=font, fill="black", anchor=a)
        else:
            bc_img = bars

        if rotation:
            bc_img = bc_img.rotate(rotation, expand=True)

        bc_img = bc_img.convert("RGBA")
        bw, bh = bc_img.size
        x, y = int(xy[0]), int(xy[1])

        # Translate anchor to top-left paste coordinate
        if anchor == "mm":
            x -= bw // 2
            y -= bh // 2
        elif anchor == "rt":
            x -= bw
        elif anchor == "rb":
            x -= bw
            y -= bh
        elif anchor == "lb":
            y -= bh

        img.paste(bc_img, (x, y), bc_img)

    def _draw_barcode_digits(
        self,
        img: Image.Image,
        display: str,
        bc_x: int,
        bc_y: int,
        bc_w: int,
        bc_h: int,
    ) -> None:
        """
        Draw EAN-13 digits vertically along the right side of the barcode,
        top-to-bottom justified so first char aligns with barcode top and
        last char aligns with barcode bottom.
        """
        chars = list(
            display
        )  # e.g. ['4',' ','9','0','1','2','3','4',' ','5','6','7','8','9','4']
        n = len(chars)
        if n < 2:
            return

        # Font size: fit each character within the per-step height
        step = bc_h / (n - 1)
        font_size = max(8, int(step * 0.9))  # slightly smaller than step → clean gap
        font = self._font(font_size)

        draw = ImageDraw.Draw(img)
        x_text = bc_x + bc_w + 2  # 2 px gap to the right of the barcode

        for i, ch in enumerate(chars):
            if ch == " ":
                continue  # space = visual break, no glyph drawn
            y_char = bc_y + round(i * step)
            draw.text((x_text, y_char), ch, font=font, fill="black", anchor="lt")

    def render_to_file(
        self, record: dict[str, Any], output_dir: str | Path, index: int = 0
    ) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Prefer sku / sku_code → jan → row index
        name_src = (
            record.get("sku")
            or record.get("sku_code")
            or record.get("jan")
            or f"row_{index}"
        )
        name = safe_filename(str(name_src).strip()) + ".png"

        dest = out / name
        self.render(record).save(dest, format="PNG")
        return dest
