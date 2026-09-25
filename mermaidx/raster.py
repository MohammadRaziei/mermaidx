"""
mermaidx.raster — SVG -> PNG via novasvg (github.com/mohammadraziei/novasvg).

The sole rasterizer as of this version: resvg_py has been retired (it
couldn't paint text inside <foreignObject> -- mermaid.js's default markup
for every diagram label -- which forced every render through a native
<text>/<tspan> fallback and a set of side-effect patches to correct for
what that fallback broke; see mermaidx.engines._svg_patches and the git
history of mermaidx.engines.quickjs_engine/v8_engine for the specifics).
novasvg paints <foreignObject> content directly (see COMPARISON.md in the
novasvg repo), so mermaid.js's own HTML-label output -- proper wrapping,
multi-line text, styled spans -- now reaches the final pixels unmodified.

Same bundled-font strategy this project has always used: mermaidx.font_metrics
measures with the bundled DejaVu Sans files, and this module paints with the
exact same files, so mermaid's layout math and the final pixels always agree
regardless of what's installed on the host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import novasvg as _novasvg

from mermaidx.png_decode import decode_png_rgba

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_FAMILY = "DejaVu Sans"

# Loaded once per process into novasvg's global font-face cache (see
# FontFace/FontFaceCache in novasvg's C++ library) -- makes "DejaVu Sans"
# resolve to exactly these bytes regardless of what's installed on the
# host, without touching the OS font config. mermaidx.font_metrics loads
# the same two files the same way, for the same reason.
_novasvg.add_font_face_from_file(_FAMILY, False, False, str(_FONTS_DIR / "DejaVuSans.ttf"))
_novasvg.add_font_face_from_file(_FAMILY, True, False, str(_FONTS_DIR / "DejaVuSans-Bold.ttf"))


def _parse_background(background: Optional[str]) -> int:
    """'#rrggbb' / '#rrggbbaa' -> packed 0xRRGGBBAA for render_to_bitmap();
    None -> fully transparent."""
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
    natural_w, natural_h = doc.width, doc.height
    if width is None and height is None:
        width, height = natural_w * scale, natural_h * scale
    elif width is None:
        # Preserve aspect ratio off the given height, same as resvg_py's
        # old behavior (and every mainstream SVG rasterizer) when only one
        # dimension is given.
        width = natural_w * (height / natural_h) if natural_h else height
    elif height is None:
        height = natural_h * (width / natural_w) if natural_w else width
    bmp = doc.render_to_bitmap(max(1, round(width)), max(1, round(height)), _parse_background(background))
    bmp.convert_to_rgba()
    return _encode_png(bmp)


def _encode_png(bmp) -> bytes:
    """novasvg's write_to_png() writes straight to a file path, not bytes --
    round-trip through a temp file to keep this module's return type
    (PNG bytes) stable regardless of how novasvg's own API evolves."""
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
    """Rasterize any SVG string to raw RGBA8888 pixels: (bytes, width, height)."""
    png_bytes = render_png(svg, background=background, width=width, height=height)
    return decode_png_rgba(png_bytes)
