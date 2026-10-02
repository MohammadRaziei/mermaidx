"""
mermaidx.raster — SVG -> PNG / JPEG / BMP / TGA via novasvg (github.com/mohammadraziei/novasvg).

The sole rasterizer as of this version: resvg_py has been retired (it
couldn't paint text inside <foreignObject> -- mermaid.js's default markup
for every diagram label -- which forced every render through a native
<text>/<tspan> fallback and a set of side-effect patches to correct for
what that fallback broke; see the git history of
mermaidx.engines.quickjs_engine/v8_engine for the specifics).
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
import novasvg.fonts as _fonts

from mermaidx.png_decode import decode_png_rgba

_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"
_FAMILY = "DejaVu Sans"

# Loaded once per process into novasvg's global font-face cache (see
# FontFace/FontFaceCache in novasvg's C++ library) -- makes "DejaVu Sans"
# resolve to exactly these bytes regardless of what's installed on the
# host, without touching the OS font config. mermaidx.font_metrics loads
# the same two files the same way, for the same reason.
_fonts.add_font_face_from_file(_FAMILY, False, False, str(_FONTS_DIR / "DejaVuSans.ttf"))
_fonts.add_font_face_from_file(_FAMILY, True, False, str(_FONTS_DIR / "DejaVuSans-Bold.ttf"))


def _parse_background(background: Optional[str]) -> int:
    """A CSS-ish color -> packed 0xRRGGBBAA for render_to_bitmap(); None
    (or empty) -> fully transparent.

    Delegates to novasvg's own Color parsers rather than hand-rolling one:
    '#rgb' / '#rgba' / '#rrggbb' / '#rrggbbaa' (the previous hand-rolled
    version only understood the last two, and silently misread '#fff' as
    0x00000fff) and the color names novasvg knows ('white', 'black', ...).
    An unparsable value raises ValueError instead of silently rendering
    some other color."""
    if not background:
        return 0x00000000
    text = str(background).strip()
    try:
        if text.startswith("#"):
            return _novasvg.Color.from_hash(text).to_int()
        return _novasvg.Color.from_name(text.lower()).to_int()
    except ValueError as exc:
        raise ValueError(
            f"Unrecognised background color {background!r} (use '#rgb', '#rrggbb', '#rrggbbaa' "
            f"or a basic color name like 'white'): {exc}"
        ) from None


# Formats novasvg's Bitmap can encode in memory (Bitmap.to_bytes()), keyed
# by every spelling we accept. "jpeg" is spelled out as an alias since both
# are common; the canonical name is what Bitmap.to_bytes() itself is given.
_IMAGE_FORMATS = {"png": "png", "jpg": "jpg", "jpeg": "jpg", "bmp": "bmp", "tga": "tga"}

# JPEG has no alpha channel: novasvg's encoder just drops it, so a
# transparent pixel (rgb 0,0,0) comes out black. A transparent-by-default
# diagram would otherwise turn into white-on-black nonsense, so JPEG
# defaults to an opaque white background instead unless the caller picks one.
_JPEG_DEFAULT_BACKGROUND = "#ffffff"


def render_bitmap(
    svg_text: str,
    *,
    scale: float = 1.0,
    background: Optional[str] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
):
    """Rasterize SVG text to a novasvg Bitmap (ARGB32 premultiplied -- the
    shape every Bitmap encoder expects; see Bitmap.to_png()'s docs)."""
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
    return doc.render_to_bitmap(max(1, round(width)), max(1, round(height)), _parse_background(background))


def render_image(
    svg_text: str,
    format: str = "png",
    *,
    scale: float = 1.0,
    background: Optional[str] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
    quality: int = 90,
) -> bytes:
    """Rasterize SVG text and encode it as ``format`` (png / jpg / jpeg /
    bmp / tga), entirely in memory -- no temp file, no Pillow.

    ``quality`` (1-100) applies to JPEG only. JPEG has no alpha, so when no
    ``background`` is given it defaults to opaque white rather than
    novasvg's transparent (which would come out black)."""
    canonical = _IMAGE_FORMATS.get(str(format).lower().lstrip("."))
    if canonical is None:
        raise ValueError(f"Unknown image format {format!r}. Supported: {', '.join(sorted(set(_IMAGE_FORMATS)))}")
    if canonical == "jpg" and background is None:
        background = _JPEG_DEFAULT_BACKGROUND
    bmp = render_bitmap(svg_text, scale=scale, background=background, width=width, height=height)
    # No bmp.convert_to_rgba() here, deliberately: the encoders already
    # unpremultiply into their own scratch buffer, so converting the
    # Bitmap in place first makes them convert a second time -- swapping
    # red/blue and corrupting semi-transparent pixels (an earlier version
    # of this module did exactly that).
    return bmp.to_bytes(canonical, quality=quality)


def render_png(
    svg_text: str,
    *,
    scale: float = 1.0,
    background: Optional[str] = None,
    width: Optional[float] = None,
    height: Optional[float] = None,
) -> bytes:
    return render_image(svg_text, "png", scale=scale, background=background, width=width, height=height)


def svg_to_png(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> bytes:
    """Rasterize any SVG string to PNG bytes (doesn't have to come from mermaidx)."""
    return render_png(svg, background=background, width=width, height=height)


def svg_to_jpg(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
    quality: int = 90,
) -> bytes:
    """Rasterize any SVG string to JPEG bytes. ``background`` defaults to
    opaque white (JPEG has no transparency)."""
    return render_image(svg, "jpg", background=background, width=width, height=height, quality=quality)


def svg_to_image(
    svg: str,
    format: str = "png",
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
    quality: int = 90,
) -> bytes:
    """Rasterize any SVG string to ``format`` bytes (png / jpg / jpeg / bmp / tga)."""
    return render_image(svg, format, background=background, width=width, height=height, quality=quality)


def svg_to_raw(
    svg: str,
    width: Optional[float] = None,
    height: Optional[float] = None,
    background: Optional[str] = None,
) -> tuple[bytes, int, int]:
    """Rasterize any SVG string to raw RGBA8888 pixels: (bytes, width, height)."""
    png_bytes = render_png(svg, background=background, width=width, height=height)
    return decode_png_rgba(png_bytes)
