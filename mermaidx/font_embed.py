"""
mermaidx.font_embed -- optional post-processing step that fixes SVG-in-a-
browser rendering (issue #12).

The rest of this package guarantees measure == paint for *our own* raster
output: font_metrics.py always measures with the bundled DejaVu Sans, and
mermaidx.raster (novasvg) always paints with that exact same file,
regardless of whatever font-family the diagram source (or mermaid's default
theme) asked for. That invariant doesn't extend to opening the raw SVG
directly in a browser: the browser has no reason to have DejaVu Sans
installed, so it substitutes whatever sans-serif font it does have for the
CSS mermaid embedded (typically `"trebuchet ms", verdana, arial,
sans-serif`), and that substitute is very unlikely to have the exact same
advance widths -- producing extra/missing whitespace around every label.

embed_dejavu_font() closes that gap for the SVG-in-a-browser case by
subsetting the bundled DejaVu font down to just the glyphs this particular
diagram actually uses (via fontTools -- ~5MB, an optional dependency, not
worth adding to every install for a browser-viewing edge case) and
registering it as a base64 @font-face under the *same* family name(s) the
diagram's own CSS already requests. Browsers prefer a matching @font-face
over any system substitution, so this doesn't require touching mermaid's
CSS at all -- it just wins the lookup mermaid already asks for.
"""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

_ASSETS_FONTS = Path(__file__).parent / "assets" / "fonts"

_FONT_FILES = {"regular": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"}
_CSS_WEIGHT = {"regular": "normal", "bold": "bold"}

_SVG_OPEN_TAG = re.compile(r"<svg\b[^>]*>")
_FONT_FAMILY_DECL = re.compile(r"font-family\s*:\s*([^;}\"']+|\"[^\"]*\"|'[^']*')")
_BOLD_WEIGHT = re.compile(r"font-weight\s*:\s*(bold|bolder|[6-9]\d\d)\b", re.IGNORECASE)
_GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}


def _unescape_xml_entities(s: str) -> str:
    """mermaid.js writes font-family names as literal &quot;-escaped text
    even inside <style> (which is PCDATA, not an attribute value -- an XML
    parser resolves this to a plain '"' either way, but our own regexes
    below run on the raw source string, so they need the same unescaping
    an XML parser would do first)."""
    return (
        s.replace("&quot;", '"').replace("&apos;", "'")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    )


def _used_characters(svg: str) -> set:
    """Every character appearing anywhere in the SVG's text content (text
    nodes, tspans, titles, ...). A superset is harmless (a handful of extra
    glyphs from e.g. the <style> block's own text costs nothing); a subset
    would silently drop glyphs, so this doesn't try to be clever about
    which elements count."""
    root = ET.fromstring(svg)
    return {ch for text in root.itertext() if text for ch in text}


def _font_weights_used(svg: str) -> set:
    """Which of the two bundled weights are actually referenced -- the same
    rule font_metrics.get_font() uses for measurement: font-weight >= 600,
    or the literal 'bold'/'bolder'."""
    weights = {"regular"}
    if _BOLD_WEIGHT.search(_unescape_xml_entities(svg)):
        weights.add("bold")
    return weights


def _font_families_used(svg: str) -> set:
    """The first (non-generic) family name in every `font-family:` CSS
    declaration in the SVG -- i.e. the exact name the browser will actually
    look up. Registering @font-face under these names (rather than e.g.
    always 'DejaVu Sans') is what lets the embedded font win the lookup
    without needing to touch mermaid's own CSS."""
    names = set()
    for m in _FONT_FAMILY_DECL.finditer(_unescape_xml_entities(svg)):
        first = m.group(1).split(",")[0].strip().strip("'\"")
        if first and first.lower() not in _GENERIC_FAMILIES:
            names.add(first)
    return names


def _subset_font_base64(weight: str, characters: set) -> str:
    import logging

    from fontTools import subset
    from fontTools.ttLib import TTFont

    logging.getLogger("fontTools").setLevel(logging.ERROR)

    font = TTFont(str(_ASSETS_FONTS / _FONT_FILES[weight]))
    options = subset.Options()
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.layout_features = []
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(characters)))
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def embed_dejavu_font(svg: str) -> str:
    """Return *svg* with inline @font-face rules for exactly the DejaVu
    Sans glyphs it uses, registered under whatever family name(s) the
    diagram's own CSS requests -- so the same font used to lay the diagram
    out also paints it in a browser, not just in mermaidx's own PNG/PDF
    output. Requires fontTools; install with `pip install mermaidx[embed]`.
    """
    try:
        from fontTools import subset  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "embed_font=True requires fontTools. Install it with:\n"
            "    pip install mermaidx[embed]"
        ) from exc

    characters = _used_characters(svg)
    families = _font_families_used(svg)
    if not characters or not families:
        return svg

    rules = []
    for weight in sorted(_font_weights_used(svg)):
        b64 = _subset_font_base64(weight, characters)
        src = f"src:url(data:font/ttf;base64,{b64}) format('truetype');"
        for family in sorted(families):
            escaped = family.replace("\\", "\\\\").replace('"', '\\"')
            rules.append(
                f'@font-face{{font-family:"{escaped}";'
                f"font-weight:{_CSS_WEIGHT[weight]};{src}}}"
            )
    style_block = "<style>" + "".join(rules) + "</style>"

    match = _SVG_OPEN_TAG.search(svg)
    if not match:
        return svg
    return svg[: match.end()] + style_block + svg[match.end():]
