"""
mermaidx.font_metrics -- just enough of the TrueType/OpenType spec to answer
one question: "how wide is this string, in this font, at this size?" (plus
the per-codepoint advance TABLE mermaidx.engines.v8_engine needs to ship
into a JS engine that can't call back into Python).

Previously this parsed the head/hhea/cmap/hmtx tables by hand (no fontTools
dependency, no kerning/ligatures -- see git history for that version). It
now delegates entirely to novasvg (github.com/mohammadraziei/novasvg), the
same library mermaidx.raster_novasvg uses to actually paint the glyphs:
novasvg's font stack is a vendored stb_truetype, exposed to Python as
FontFace/Font (novasvg.FontFace.codepoints()/advance_width_units()/
units_per_em, novasvg.Font.measure_text()). One engine measuring AND
painting means layout and paint can't drift apart from two separately
maintained implementations -- which is the whole reason novasvg itself
exists (see its README / COMPARISON.md).

Verified numerically identical to the old hand-rolled parser for the
bundled DejaVu Sans files: same width, same ascent (descent differs only in
sign convention, normalized below to keep this module's own established
convention of "positive descent"), same unitsPerEm/ascender/descender/
notdef-glyph width, and the exact same 5906 codepoints with the exact same
per-codepoint advance in font design units.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import novasvg as _novasvg

_ASSETS_FONTS = Path(__file__).parent / "assets" / "fonts"
_FAMILY = "DejaVu Sans"

# Registered once per process into novasvg's global font-face cache -- same
# pattern raster.py uses for the paint side, so "DejaVu Sans" resolves to
# these exact bytes for both layout and paint regardless of what's
# installed on the host.
_novasvg.add_font_face_from_file(_FAMILY, False, False, str(_ASSETS_FONTS / "DejaVuSans.ttf"))
_novasvg.add_font_face_from_file(_FAMILY, True, False, str(_ASSETS_FONTS / "DejaVuSans-Bold.ttf"))


class Font:
    """A bundled font family (regular or bold), backed by a novasvg
    FontFace. Public shape kept identical to the old hand-rolled Font class
    on purpose -- both engines/quickjs_engine.py (measure(), synchronous
    per-string) and engines/v8_engine.py (full_advance_table() /
    notdef_advance_units() / metrics_summary(), one-time bulk export) use
    it unchanged."""

    def __init__(self, bold: bool) -> None:
        self._face = _novasvg.get_font_face(_FAMILY, bold, False)

    @lru_cache(maxsize=None)
    def _at_size(self, size_px: float) -> "_novasvg.Font":
        return _novasvg.Font(self._face, size_px)

    # -- per-string measurement (quickjs_engine's synchronous-callback path) --

    def measure(self, text: str, size_px: float) -> dict:
        font = self._at_size(size_px)
        return {
            "width": font.measure_text(text),
            "ascent": font.ascent,
            "descent": -font.descent,  # novasvg: negative; this module's convention: positive
        }

    # -- size-independent bulk export (v8_engine's no-callback path) --

    def full_advance_table(self) -> dict:
        """Every codepoint this font can render, mapped to its advance
        width in font design units (unscaled, i.e. independent of
        size_px) -- lets a JS engine that has this table (plus
        metrics_summary()) reproduce measure() exactly by summing itself,
        with zero Python callback involved."""
        return {cp: self._face.advance_width_units(cp) for cp in self._face.codepoints()}

    def notdef_advance_units(self) -> float:
        """Advance width used for any codepoint outside the font's cmap
        (the ".notdef" glyph) -- matches what measure()/
        full_advance_table() themselves fall back to for such a codepoint."""
        return self._face.notdef_advance_width_units

    def metrics_summary(self) -> dict:
        """unitsPerEm/ascender/descender -- everything besides the
        advance table itself that's needed to reproduce measure() in JS."""
        return {
            "unitsPerEm": self._face.units_per_em,
            "ascender": self._face.ascent_units,
            "descender": self._face.descent_units,
        }


# ── font selection ────────────────────────────────────────────────────────

_REGULAR = Font(bold=False)
_BOLD = Font(bold=True)


def get_font(weight: Optional[str] = None) -> Font:
    """
    Only one bundled font family (DejaVu Sans) is used regardless of the
    diagram's requested font-family: mermaid diagrams don't depend on exact
    typeface, only on consistent, real metrics between layout and paint --
    and this stays true only if both stages read the *same* font file.
    """
    try:
        if int(weight or 0) >= 600:
            return _BOLD
    except (TypeError, ValueError):
        pass
    if str(weight).strip().lower() in ("bold", "bolder"):
        return _BOLD
    return _REGULAR
