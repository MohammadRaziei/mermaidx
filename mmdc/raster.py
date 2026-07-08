"""
mmdc.raster — SVG -> PNG via resvg_py.

`skip_system_fonts=True` + explicit `font_files` means every render uses
exactly the same bundled DejaVu Sans files that mmdc.font_metrics reads for
layout measurement (see engine.py) — the whole point being that mermaid's
layout and the final pixels always agree, regardless of what fonts (if any)
happen to be installed on the host system.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import resvg_py

from mmdc.png_decode import decode_png_rgba

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_FONT_FILES = [
    str(_FONTS_DIR / "DejaVuSans.ttf"),
    str(_FONTS_DIR / "DejaVuSans-Bold.ttf"),
]
_FAMILY = "DejaVu Sans"


def render_png(
    svg_text: str,
    *,
    scale: float = 1.0,
    background: Optional[str] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
) -> bytes:
    return bytes(resvg_py.svg_to_bytes(
        svg_string=svg_text,
        background=background,
        width=width,
        height=height,
        zoom=scale if not (width or height) else None,
        skip_system_fonts=True,
        font_files=_FONT_FILES,
        font_family=_FAMILY,
        sans_serif_family=_FAMILY,
        serif_family=_FAMILY,
        cursive_family=_FAMILY,
        fantasy_family=_FAMILY,
        monospace_family=_FAMILY,
    ))


def svg_to_png(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> bytes:
    """Rasterize any SVG string to PNG bytes (doesn't have to come from mmdc)."""
    return render_png(svg, background=background, width=width, height=height)


def svg_to_raw(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> tuple[bytes, int, int]:
    """Rasterize any SVG string to raw RGBA8888 pixels: (bytes, width, height)."""
    png_bytes = render_png(svg, background=background, width=width, height=height)
    return decode_png_rgba(png_bytes)
