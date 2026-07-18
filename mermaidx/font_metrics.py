"""
mermaidx.font_metrics — just enough of the TrueType/OpenType spec to answer one
question: "how wide is this string, in this font, at this size?"

This intentionally does NOT use fontTools (a real, excellent library — but
~20MB for what amounts to a handful of table lookups here) or any other
third-party dependency. It reads exactly three tables:

  head  -> unitsPerEm
  hhea  -> numberOfHMetrics, ascender, descender
  cmap  -> Unicode codepoint -> glyph ID (format 4 and format 12 subtables)
  hmtx  -> glyph ID -> advance width

No kerning, no ligatures, no complex shaping — just summed per-character
advance widths. For mermaid's own layout purposes (sizing boxes around
short labels) this is the same level of precision most non-browser SVG
tools operate at, and it exactly matches what will actually be painted
since the *same* bundled font file is also handed to resvg for final
rendering (see engine.py).
"""

from __future__ import annotations

import struct
from functools import lru_cache
from pathlib import Path
from typing import Optional


class _Reader:
    __slots__ = ("data",)

    def __init__(self, data: bytes) -> None:
        self.data = data

    def u8(self, off): return self.data[off]
    def u16(self, off): return struct.unpack_from(">H", self.data, off)[0]
    def i16(self, off): return struct.unpack_from(">h", self.data, off)[0]
    def u32(self, off): return struct.unpack_from(">I", self.data, off)[0]


class Font:
    """A single parsed TTF/OTF file's metrics (no glyph outlines)."""

    def __init__(self, path: Path) -> None:
        r = self._r = _Reader(path.read_bytes())
        num_tables = r.u16(4)
        self._tables = {}
        for i in range(num_tables):
            rec = 12 + i * 16
            tag = r.data[rec:rec + 4].decode("latin-1")
            offset = r.u32(rec + 8)
            length = r.u32(rec + 12)
            self._tables[tag] = (offset, length)

        head_off, _ = self._tables["head"]
        self.units_per_em = r.u16(head_off + 18)

        hhea_off, _ = self._tables["hhea"]
        self.ascender = r.i16(hhea_off + 4)
        self.descender = r.i16(hhea_off + 6)
        self._num_h_metrics = r.u16(hhea_off + 34)

        hmtx_off, _ = self._tables["hmtx"]
        self._hmtx_off = hmtx_off
        self._advance_cache: dict[int, int] = {}

        self._cmap = self._parse_cmap()

    # -- cmap: codepoint -> glyph id --------------------------------------

    def _parse_cmap(self) -> dict:
        r = self._r
        cmap_off, _ = self._tables["cmap"]
        num_subtables = r.u16(cmap_off + 2)
        best_offset = None
        best_score = -1
        for i in range(num_subtables):
            rec = cmap_off + 4 + i * 8
            platform_id = r.u16(rec)
            encoding_id = r.u16(rec + 2)
            offset = r.u32(rec + 4)
            # Prefer Windows BMP (3,1), then Windows full-unicode (3,10),
            # then Unicode platform (0,*), skipping symbol/Mac tables.
            score = {(3, 10): 3, (3, 1): 2, (0, 4): 2, (0, 3): 2}.get(
                (platform_id, encoding_id), 0
            )
            if score > best_score:
                best_score, best_offset = score, cmap_off + offset
        if best_offset is None:
            return {}

        fmt = r.u16(best_offset)
        mapping: dict = {}
        if fmt == 4:
            seg_x2 = r.u16(best_offset + 6)
            seg_count = seg_x2 // 2
            end_base = best_offset + 14
            start_base = end_base + seg_x2 + 2
            delta_base = start_base + seg_x2
            range_base = delta_base + seg_x2
            for s in range(seg_count):
                end = r.u16(end_base + s * 2)
                start = r.u16(start_base + s * 2)
                delta = r.i16(delta_base + s * 2)
                range_offset = r.u16(range_base + s * 2)
                if start == 0xFFFF and end == 0xFFFF:
                    continue
                for cp in range(start, min(end, 0xFFFE) + 1):
                    if range_offset == 0:
                        gid = (cp + delta) & 0xFFFF
                    else:
                        addr = range_base + s * 2 + range_offset + (cp - start) * 2
                        if addr + 2 > len(r.data):
                            continue
                        gid = r.u16(addr)
                        if gid != 0:
                            gid = (gid + delta) & 0xFFFF
                    if gid:
                        mapping[cp] = gid
        elif fmt == 12:
            num_groups = r.u32(best_offset + 12)
            for g in range(num_groups):
                base = best_offset + 16 + g * 12
                start_char = r.u32(base)
                end_char = r.u32(base + 4)
                start_gid = r.u32(base + 8)
                for cp in range(start_char, end_char + 1):
                    mapping[cp] = start_gid + (cp - start_char)
        # else: unsupported subtable format (0, 6, ...) -> empty mapping;
        # advance_width() falls back to glyph 0 for every character.
        return mapping

    # -- hmtx: glyph id -> advance width -----------------------------------

    def _glyph_advance(self, gid: int) -> int:
        cached = self._advance_cache.get(gid)
        if cached is not None:
            return cached
        r = self._r
        if gid < self._num_h_metrics:
            width = r.u16(self._hmtx_off + gid * 4)
        else:
            # glyphs beyond numberOfHMetrics repeat the last advance width
            width = r.u16(self._hmtx_off + (self._num_h_metrics - 1) * 4)
        self._advance_cache[gid] = width
        return width

    # -- public ---------------------------------------------------------------

    def advance_width_units(self, text: str) -> int:
        """Sum of glyph advance widths for `text`, in font design units."""
        total = 0
        for ch in text:
            gid = self._cmap.get(ord(ch), 0)
            total += self._glyph_advance(gid)
        return total

    def measure(self, text: str, size_px: float) -> dict:
        scale = size_px / self.units_per_em
        return {
            "width": self.advance_width_units(text) * scale,
            "ascent": self.ascender * scale,
            "descent": -self.descender * scale,  # descender is negative in the font
        }

    def full_advance_table(self) -> dict:
        """Every codepoint this font can render, mapped to its advance
        width in font design units (unscaled, i.e. independent of size_px).

        Since measure()/advance_width_units() do nothing more than sum
        per-character advances (no kerning, no ligatures -- see module
        docstring), a JS engine that has this table (plus units_per_em/
        ascender/descender, see metrics_summary()) can reproduce measure()
        exactly by summing itself, with zero Python callback involved. This
        is what mermaidx.engines.v8_engine uses, since its underlying V8
        binding can't do synchronous Python callbacks the way QuickJS can.
        """
        return {cp: self._glyph_advance(gid) for cp, gid in self._cmap.items()}

    def notdef_advance_units(self) -> int:
        """Advance width used for any codepoint outside the font's cmap
        (glyph id 0, the ".notdef" glyph) -- matches what
        advance_width_units() falls back to via `self._cmap.get(ord(ch), 0)`."""
        return self._glyph_advance(0)

    def metrics_summary(self) -> dict:
        """units_per_em/ascender/descender -- everything besides the
        advance table itself that's needed to reproduce measure() in JS."""
        return {
            "unitsPerEm": self.units_per_em,
            "ascender": self.ascender,
            "descender": self.descender,
        }


# ── font selection ────────────────────────────────────────────────────────

_ASSETS_FONTS = Path(__file__).parent / "assets" / "fonts"


@lru_cache(maxsize=None)
def _load(name: str) -> Font:
    return Font(_ASSETS_FONTS / name)


def get_font(weight: Optional[str] = None) -> Font:
    """
    Only one bundled font family (DejaVu Sans) is used regardless of the
    diagram's requested font-family: mermaid diagrams don't depend on exact
    typeface, only on consistent, real metrics between layout and paint —
    and this stays true only if both stages read the *same* font file.
    """
    try:
        if int(weight or 0) >= 600:
            return _load("DejaVuSans-Bold.ttf")
    except (TypeError, ValueError):
        pass
    if str(weight).strip().lower() in ("bold", "bolder"):
        return _load("DejaVuSans-Bold.ttf")
    return _load("DejaVuSans.ttf")
