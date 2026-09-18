"""
mermaidx.raster_novasvg — SVG -> PNG via novasvg (github.com/mohammadraziei/novasvg).

Drop-in alternative to mermaidx.raster (resvg_py). Same public interface
(render_png/svg_to_png/svg_to_raw), same bundled-font strategy as raster.py
for the same reason: mermaid's own layout math (mermaidx.font_metrics) and
the pixels painted here must agree on the exact same font files, regardless
of what's installed on the host.

Why this backend exists at all: resvg cannot render text inside
<foreignObject> -- mermaid.js's default markup for every diagram label --
so mermaidx has historically had to force mermaid into its native
<text>/<tspan> fallback (see mermaidx.engines._svg_patches and the
textPlacement overrides in engines/quickjs_engine.py and
engines/v8_engine.py) and then patch several rendering side effects of that
fallback by hand. novasvg renders <foreignObject> text directly (see
COMPARISON.md in the novasvg repo), so a diagram rendered through *this*
module does not need those patches or the textPlacement override -- but
that removal is a separate, deliberate follow-up (it changes what mermaid.js
itself emits, not just how it's rasterized), not bundled into this file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import novasvg as _novasvg

from mermaidx.png_decode import decode_png_rgba

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_FAMILY = "DejaVu Sans"

# Loaded once per process, mirroring raster.py's _FONT_FILES/_FAMILY pair.
# novasvg's font cache is global (see FontFaceCache in the C++ library), so
# -- like resvg_py's skip_system_fonts=True + font_files= -- this makes
# "DejaVu Sans" resolve to exactly these bytes regardless of what's
# installed on the host, without touching the OS font config.
_novasvg.add_font_face_from_file(_FAMILY, False, False, str(_FONTS_DIR / "DejaVuSans.ttf"))
_novasvg.add_font_face_from_file(_FAMILY, True, False, str(_FONTS_DIR / "DejaVuSans-Bold.ttf"))


def _parse_background(background: Optional[str]) -> int:
    """'#rrggbb' / '#rrggbbaa' -> packed 0xRRGGBBAA for render_to_bitmap();
    None -> fully transparent, matching resvg_py's untouched background."""
    if not background:
        return 0x00000000
    h = background.lstrip("#")
    if len(h) == 6:
        h += "ff"
    return int(h, 16)


def render_png(
    svg_text: str,
    *,
    scale: float = 1.0,
    background: Optional[str] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
) -> bytes:
    doc = _novasvg.Document.load_from_data(svg_text)
    if width is None and height is None:
        width = doc.width * scale
        height = doc.height * scale
    bmp = doc.render_to_bitmap(int(width), int(height), _parse_background(background))
    bmp.convert_to_rgba()
    return _encode_png(bmp)


def _encode_png(bmp) -> bytes:
    """novasvg's write_to_png() writes straight to a file path, not bytes --
    round-trip through a temp file to keep this module's return type
    (PNG bytes) identical to raster.py's, so DiagramBase never has to know
    which backend produced them."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as f:
        bmp.write_to_png(f.name)
        f.seek(0)
        return f.read()


def svg_to_png(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> bytes:
    """Rasterize any SVG string to PNG bytes (doesn't have to come from mermaidx)."""
    return render_png(svg, background=background, width=width, height=height)


def svg_to_raw(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> tuple[bytes, int, int]:
    """Rasterize any SVG string to raw RGBA8888 pixels: (bytes, width, height).

    Goes through the same PNG round-trip as render_png() rather than
    bmp.numpy() directly, so the raw bytes this returns are decoded by the
    exact same png_decode path raster.py uses -- keeping both backends'
    numpy/raw output bit-identical in format even if their PNG encoders
    ever diverge.
    """
    png_bytes = render_png(svg, background=background, width=width, height=height)
    return decode_png_rgba(png_bytes)
