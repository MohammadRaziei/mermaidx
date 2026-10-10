"""mermaidx's SVG vs the SVG real mermaid-cli (mmdc) produces for the same diagram -- byte for byte.

The references next to each sample in tests/samples/ come from mmdc running mermaid.js in Chromium with
DejaVu Sans (see tests/samples/README.md for the exact recipe). mermaidx runs the same mermaid.js and does for
it what mmdc's page does (see mermaidx/assets/mmdc_driver.js): render into #container, round-trip the SVG
text through the HTML parser, set the background colour through CSSOM, serialize with XMLSerializer. So
nothing is normalised here except the ids mermaid.js itself draws at random (RANDOM_IDS below): the
references would not match a second mmdc run on those either.
"""
import glob
import os
import re

import pytest

import mermaidx

HERE = os.path.dirname(__file__)
SAMPLES = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "samples", "*.mmd")))

# Ids mermaid.js generates from Math.random()/a hash on every run, in mmdc as much as in mermaidx:
#   state diagrams:  <svg-id>-state-id-<random>-<n>   (mermaid's generateId)
#   architecture:    IconifyId<random hex>             (the icon renderer's own id)
RANDOM_IDS = [
    (re.compile(r"(state-id)-[0-9a-z]+-"), r"\1-#-"),
    (re.compile(r"IconifyId[0-9a-f]+"), "IconifyId#"),
]


def _mask(svg):
    for pattern, replacement in RANDOM_IDS:
        svg = pattern.sub(replacement, svg)
    return svg


# Samples whose SVG still differs from mmdc's, each with what is known about why. These are strict
# xfails: the day one of them starts matching, the suite fails and the entry has to be removed here.
KNOWN_DIFFERENT = {
    "21_xychart": "bar x/width come back from Chrome as single-precision values (91.34687690734863); "
                  "where that float32 round-trip happens is not found yet",
    "22_sankey": "viewBox y differs by one float32 ulp; most likely Chrome (Skia) computes the bbox of the "
                 "bezier link paths in single precision, mermaidx does it in double and rounds at the end",
    "24_c4_context": "Chrome writes the <image> href as xlink:href (the shim drops the namespace) and the "
                     "shapes are placed differently (699,464 vs 200,700); not investigated further",
    "30_treemap": "the ref keeps the raw style attribute ('font-size: 38px;fill:#ffffff;') where mermaidx "
                  "re-serializes it, and the viewBox differs; not investigated further",
    "32_ishikawa": "text sizes and positions differ (viewBox width 693 vs 501); cause not found yet",
    "39_mindmap_shapes": "node/edge coordinates differ (cytoscape layout inputs); cause not found yet",
    "42_flowchart_markdown_labels": "inline <strong>/<em> in a foreignObject label: novasvg's ForeignObjectSimple "
                                    "strips tags to plain text, so bold runs are measured regular "
                                    "('Group one' 83.57 vs Chrome 89.72 = bold('Group') + regular(' one'))",
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
