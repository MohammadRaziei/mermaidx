"""mermaidx's SVG vs the SVG real mermaid-cli (mmdc) produces for the same diagram -- byte for byte.

The references next to each sample in tests/samples/ come from mmdc running mermaid.js in Chromium with
DejaVu Sans (see tests/samples/README.md for the exact recipe). mermaidx runs the same mermaid.js and does for
it what mmdc's page does (see mermaidx/assets/mmdc_driver.js): render into #container, round-trip the SVG
text through the HTML parser, set the background colour through CSSOM, serialize with XMLSerializer. So
nothing is normalised here except the ids mermaid.js itself draws at random (svg_compare.RANDOM_IDS): the
references would not match a second mmdc run on those either.
"""
import glob
import os
import re

import pytest

import mermaidx
from svg_compare import mask_random_ids as _mask

HERE = os.path.dirname(__file__)
SAMPLES = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "samples", "*.mmd")))

# Samples whose SVG still differs from mmdc's, each with what is known about why. These are strict
# xfails: the day one of them starts matching, the suite fails and the entry has to be removed here.
KNOWN_DIFFERENT = {
    "21_xychart": "bar x/width come back from Chrome as single-precision values (91.34687690734863); "
                  "where that float32 round-trip happens is not found yet",
    "24_c4_context": "Chrome writes the <image> href as xlink:href (the shim drops the namespace) and the "
                     "shapes are placed differently (699,464 vs 200,700); not investigated further",
    "42_flowchart_markdown_labels": "a label of several text runs is 1/64 px narrower than Chrome's: Chrome rounds "
                                    "every run up to a LayoutUnit and adds, mermaidx rounds the sum "
                                    "(155.28125 vs 155.296875); the same document within tolerance",
    "32_ishikawa": "text sizes and positions differ (viewBox width 693 vs 501); cause not found yet",
}


@pytest.mark.parametrize(
    "name",
    [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN_DIFFERENT[n])) if n in KNOWN_DIFFERENT else n
     for n in SAMPLES],
)
def test_svg_is_byte_identical_to_mmdc(name):
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    ref = open(os.path.join(HERE, "samples", name + ".svg"), encoding="utf-8").read()
    ours = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    assert _mask(ours) == _mask(ref)


@pytest.mark.parametrize("name", ["06_complex_sequence", "38_class_advanced", "01_simple_flowchart"])
def test_rendering_twice_gives_the_same_bytes(name):
    """mmdc opens a fresh page per diagram, so mermaid.js's id counters (actor1, classId-Animal-0, ...) always
    start from zero. Each mermaidx render must start from the same state, whatever was rendered before."""
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    first = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    second = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    assert first == second
