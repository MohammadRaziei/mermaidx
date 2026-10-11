"""mermaidx's SVG vs mmdc's, parsed and compared element by element (tests/svg_compare.py): the same elements in
the same order with the same attributes and text, and every number approximately equal. test_mmdc_reference.py
asks for the same bytes; this one is what is left once float32 noise (a last digit or two) does not count --
it needs no Chrome-exact arithmetic, only that the document is the same document."""
import glob
import os

import pytest

import mermaidx
import svg_compare as sc

HERE = os.path.dirname(__file__)
SAMPLES = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "samples", "*.mmd")))

# Samples that are really a different document, not float noise (no tolerance makes them agree). Each says what
# the first differences are; the cause is not established. Strict xfails: when one starts to agree the suite
# fails and the entry goes.
KNOWN_DIFFERENT = {
    "24_c4_context": "viewBox 1843x1512 vs 1136x2065; <image> carries `href` where the reference has `xlink:href`",
    "30_treemap": "svg viewBox y/height differ by 2.5 (`2 24.5 996 373.5` vs `2 27 996 371`); the shim's text getBBox "
                  "ignores dominant-baseline, which Chrome applies (probed, 12px at y=12.5: alphabetic 1.5, middle "
                  "4.78 = x-height/2 lower, central 5.5 = (ascent-descent)/2 lower) -- likely, not shown, the only cause",
    "32_ishikawa": "layout differs (viewBox width 693 vs 501, line x1 -531.97 vs -389.67)",
    "42_flowchart_markdown_labels": "foreignObject label widths differ (886.28 vs 897.78): novasvg measures "
                                    "inline <strong>/<em> runs as regular text",
}


@pytest.mark.parametrize(
    "name",
    [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN_DIFFERENT[n])) if n in KNOWN_DIFFERENT else n
     for n in SAMPLES],
)
def test_svg_is_the_same_document_as_mmdc(name):
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    ref = open(os.path.join(HERE, "samples", name + ".svg"), encoding="utf-8").read()
    ours = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    diffs = sc.compare(sc.parse(sc.mask_random_ids(ours)), sc.parse(sc.mask_random_ids(ref)))
    assert not diffs, f"{len(diffs)} differences, first:\n" + "\n".join(diffs[:5])
