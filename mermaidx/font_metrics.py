"""
mermaidx.font_metrics -- just enough of the TrueType/OpenType spec to answer
one question: "how wide is this string, in this font, at this size?" (plus
the per-codepoint advance and kerning TABLES mermaidx.engines.v8_engine
needs to ship into a JS engine that can't call back into Python).

Previously this parsed the head/hhea/cmap/hmtx tables by hand (no fontTools
dependency, no kerning/ligatures -- see git history for that version). It
now delegates entirely to novasvg (github.com/mohammadraziei/novasvg), the
same library mermaidx.raster uses to actually paint the glyphs: novasvg's
font stack is a vendored stb_truetype, exposed to Python as
novasvg.fonts.FontFace/Font (FontFace.codepoints()/advance_width_units()/
units_per_em, Font.measure_text()). One engine measuring AND
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

import novasvg.fonts as _fonts

_ASSETS_FONTS = Path(__file__).parent / "assets" / "fonts"
_FAMILY = "DejaVu Sans"

# Registered once per process into novasvg's global font-face cache -- same
# pattern raster.py uses for the paint side, so "DejaVu Sans" resolves to
# these exact bytes for both layout and paint regardless of what's
# installed on the host.
_fonts.add_font_face_from_file(_FAMILY, False, False, str(_ASSETS_FONTS / "DejaVuSans.ttf"))
_fonts.add_font_face_from_file(_FAMILY, True, False, str(_ASSETS_FONTS / "DejaVuSans-Bold.ttf"))


class Font:
    """A bundled font family (regular or bold), backed by a novasvg
    FontFace. Public shape kept identical to the old hand-rolled Font class
    on purpose -- both engines/quickjs_engine.py (measure(), synchronous
    per-string) and engines/v8_engine.py (full_advance_table() /
    notdef_advance_units() / metrics_summary(), one-time bulk export) use
    it unchanged."""

    def __init__(self, bold: bool) -> None:
        self._face = _fonts.get_font_face(_FAMILY, bold, False)

    @lru_cache(maxsize=None)
    def _at_size(self, size_px: float) -> "_fonts.Font":
        return _fonts.Font(self._face, size_px)

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

    def ascii_kerning_pairs(self) -> dict:
        """Sparse kerning-adjustment table (raw font design units) for
        every printable-ASCII codepoint pair with a nonzero
        kern/GPOS adjustment, keyed "cp1,cp2" -> units.

        Why ASCII-scoped rather than exhaustive: see
        novasvg.fonts.FontFace.kern_advance_units()'s own docstring for why
        there's no cheap bulk enumeration of a font's *whole* kerning table
        the way there is for its cmap (full_advance_table()) -- this
        queries the O(95^2) printable-ASCII pairs one at a time instead
        (still a fraction of a second; see this method's own call site),
        which covers virtually all of a real diagram's actual text without
        the cost of querying all ~35M pairs a 5906-codepoint font's full
        cross product would need. A pair with no adjustment (the vast
        majority) is left out entirely, keeping the shipped table small.

        Exists only for mermaidx.engines.v8_engine, which -- unlike
        quickjs_engine.py, which can call measure() itself per string --
        has to reproduce Font::measureText()'s per-glyph-pair kerning
        lookup as a local JS sum instead (see that module's
        measureFull())."""
        table = {}
        codepoints = range(0x20, 0x7F)
        for a in codepoints:
            for b in codepoints:
                k = self._face.kern_advance_units(a, b)
                if k:
                    table[f"{a},{b}"] = k
        return table

    def metrics_summary(self) -> dict:
        """unitsPerEm/ascender/descender -- everything besides the
        advance table itself that's needed to reproduce measure() in JS."""
        return {
            "unitsPerEm": self._face.units_per_em,
            "ascender": self._face.ascent_units,
            "descender": self._face.descent_units,
        }

    # -- <foreignObject> HTML label sizing (quickjs_engine's headless DOM shim) --

    def foreign_object_metrics(self, html: str, size_px: float) -> dict:
        """Height/width (and line count/line-height) novasvg's own
        ForeignObjectSimple::render() will use when it later paints `html`
        at this size -- see novasvg.fonts.measure_foreign_object()'s docstring
        for why delegating to novasvg for this (rather than mermaidx
        reimplementing its own line-counting logic) is what keeps a node
        box mermaid.js sizes during headless layout from disagreeing with
        what novasvg then actually paints into it."""
        return _fonts.measure_foreign_object(html, self._at_size(size_px))


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
