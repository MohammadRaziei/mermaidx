"""
Regression tests using a small corpus of real Mermaid source files, each
paired with a reference SVG rendered by mermaid.ink (the official/browser
rendering, via a real Chrome instance).

These caught real bugs this package's own hand-written test diagrams never
exercised: stadium-shaped nodes and stateDiagram start/end circles crashed
outright (missing `RegExp.$1` legacy static properties -- QuickJS-ng doesn't
implement them, but a roughjs-derived path parser bundled in mermaid.js
relies on them; and missing `Element.children`/`.matches()` in the DOM
shim), and mindmap needs `crypto.getRandomValues` (now polyfilled) plus a
full Canvas 2D context (not yet implemented -- see the xfail below).

Comparison is structural (label words + aspect ratio), not pixel-diffing --
two different rendering engines are never going to match pixel-for-pixel.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mermaidx

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_NAMES = sorted(p.stem for p in SAMPLES_DIR.glob("*.mmd"))


def _svg_texts(svg_str: str) -> list[str]:
    """All human-readable label text in an SVG -- plain <text>/<tspan> or
    HTML wrapped inside a <foreignObject> (<div>/<span>/<p>). Skips
    <style>/<script>, which carry CSS/JS text, not labels."""
    root = ET.fromstring(svg_str)
    skip = {"style", "script"}
    return sorted(
        el.text.strip()
        for el in root.iter()
        if el.tag.split("}")[-1] not in skip and el.text and el.text.strip()
    )


def _svg_aspect_ratio(svg_str: str) -> float:
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_str)
    assert m, "no viewBox found"
    _, _, w, h = (float(x) for x in m.group(1).split())
    return w / h


# mindmap needs a full Canvas 2D context shim (cytoscape's internal
# renderer uses <canvas> directly) -- a much bigger undertaking than the
# other fixes here. Tracked as a known gap rather than silently skipped.
KNOWN_UNSUPPORTED = {"05_simple_mindmap"}


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_sample_renders_without_error(name):
    if name in KNOWN_UNSUPPORTED:
        pytest.xfail(f"{name}: needs a Canvas 2D context shim (not yet implemented)")
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    d = mermaidx.render(source)
    assert d.svg().startswith("<svg")


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_labels_match_reference(name):
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    reference_svg = (SAMPLES_DIR / f"{name}.svg").read_text(encoding="utf-8")

    ours = mermaidx.render(source).svg()

    reference_words = sorted(" ".join(_svg_texts(reference_svg)).split())
    our_words = sorted(" ".join(_svg_texts(ours)).split())
    assert our_words == reference_words, (
        f"label text mismatch for {name!r}:\n"
        f"  reference: {reference_words}\n"
        f"  ours:      {our_words}"
    )


# Same rationale as test_online_comparison.py's ASPECT_DIAGRAMS split: aspect
# ratio is only a meaningful cross-check when node labels are short enough
# that real CSS word-wrap (mermaid.ink, htmlLabels:true) vs this package's
# htmlLabels:false doesn't change node proportions much either way. For
# flowchart/ER diagrams with substantial label text, that wrapping decision
# measurably changes the whole diagram's shape -- a known, accepted
# trade-off (see engine.py), not something to chase with an ever-looser
# tolerance. The label-content check above still applies to all of them.
ASPECT_RATIO_MEANINGFUL_FOR = {"03_simple_sequence", "04_simple_state", "06_complex_sequence"}


@pytest.mark.parametrize("name", sorted(ASPECT_RATIO_MEANINGFUL_FOR))
def test_sample_aspect_ratio_close_to_reference(name):
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    reference_svg = (SAMPLES_DIR / f"{name}.svg").read_text(encoding="utf-8")

    ours = mermaidx.render(source).svg()

    reference_ratio = _svg_aspect_ratio(reference_svg)
    our_ratio = _svg_aspect_ratio(ours)
    rel_diff = abs(our_ratio - reference_ratio) / reference_ratio
    assert rel_diff < 0.35, (
        f"aspect ratio for {name!r} differs too much: "
        f"ours={our_ratio:.3f} reference={reference_ratio:.3f} (delta={rel_diff:.0%})"
    )


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_png_and_pdf_also_work(name):
    """The SVG comparisons above are the interesting part; this just makes
    sure the rest of the pipeline (resvg, the PDF writer) doesn't choke on
    any of these samples either."""
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    d = mermaidx.render(source)
    assert d.png()[:8] == b"\x89PNG\r\n\x1a\n"
    assert d.pdf()[:5] == b"%PDF-"
