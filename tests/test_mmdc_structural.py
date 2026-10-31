"""mermaidx's SVG vs mmdc's, parsed with pygixml and compared node by node (tests/svg_compare.py): the same
elements, attributes, text, comments and whitespace in the same order, nothing more or less on either side. Only
the numbers get a tolerance (float round-off and layout rounding, up to one pixel); they do not have to be the
same digits. The few ids mermaid.js draws at random are masked, in the reference as much as here.
"""
import glob
import os
import sys

import pytest

import mermaidx
import svg_compare as sc

HERE = os.path.dirname(__file__)
SAMPLES = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "samples", "*.mmd")))

BACKENDS = ("quickjs", "v8")  # the engines (of js:mermaid)

# (backend, sample) -> why it differs from mmdc. strict xfail: the day one of these starts to match, the test fails
# and the entry has to go.
KNOWN_DIFFERENT = {
    # mmdc 12 measures text with Chrome's own layout: it snaps fractional font sizes (c4's 11.48px, for one) to a
    # grid of about 1/64 px before measuring, and mermaid.js then wraps or sizes by those widths. The shim does not
    # hand-round to copy that, so where a width lands on the other side of a wrapping or sizing threshold the whole
    # layout moves (15 to 22 px), which no per-number tolerance covers.
    ("quickjs", "24_c4_context"): (
        "Chrome text layout, see above: a c4 label wraps onto two lines here and stays on one line in mmdc (node 216 px wide instead of 236.7 px)"
    ),
    ("v8", "24_c4_context"): (
        "Chrome text layout, see above: a c4 label wraps onto two lines here and stays on one line in mmdc (node 216 px wide instead of 236.7 px)"
    ),
    ("quickjs", "37_erd_relations"): (
        "Chrome text layout, see above: entity widths differ (viewBox 673 px wide instead of 695 px), so the edges are routed differently"
    ),
    ("v8", "37_erd_relations"): (
        "Chrome text layout, see above: entity widths differ (viewBox 673 px wide instead of 695 px), so the edges are routed differently"
    ),
    ("quickjs", "38_class_advanced"): (
        "Chrome text layout, see above: class box heights differ (viewBox 394.5 px high instead of 389 px), so the edges are routed differently"
    ),
    ("v8", "38_class_advanced"): (
        "Chrome text layout, see above: class box heights differ (viewBox 394.5 px high instead of 389 px), so the edges are routed differently"
    ),
    ("v8", "39_mindmap_shapes"): (
        "cose-bilkent runs one cooling cycle more than with quickjs. Math.sin of mini-racer's V8 differs by 1 ulp "
        "from quickjs/libm (sin(-5.969026041820607), sin(0.5569781975426904)); replaying quickjs's Math.sin results "
        "in V8 gives 0 differences. Why mini-racer's sin differs (V8 version / build flags) is not known."
    ),
}


# Same sample, other cause: quickjs calls the libm of the platform. On macOS (CI, macos-latest) the output of
# quickjs is the same as that of V8 on Linux (viewBox, edge `d` and `data-points` compared one by one), not the
# one of mmdc. Only measured for this sample and only on macOS; Windows is not known.
KNOWN_DIFFERENT_ON = {
    ("darwin", "quickjs", "39_mindmap_shapes"): (
        "libm of macOS gives other Math results than the reference, so cose-bilkent ends in another cooling cycle"
    ),
}


def _known_different(backend, name):
    return KNOWN_DIFFERENT.get((backend, name)) or KNOWN_DIFFERENT_ON.get((sys.platform, backend, name))


def _cases():
    for backend in BACKENDS:
        for name in SAMPLES:
            marks = []
            reason = _known_different(backend, name)
            if reason:
                marks.append(pytest.mark.xfail(strict=True, reason=reason))
            yield pytest.param(backend, name, marks=marks, id=f"{backend}-{name}")


@pytest.mark.parametrize("backend, name", list(_cases()))
def test_svg_is_the_same_document_as_mmdc(backend, name):
    if backend == "v8":
        pytest.importorskip("py_mini_racer")
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    ref = open(os.path.join(HERE, "samples", name + ".svg"), encoding="utf-8").read()
    ours = mermaidx.render(src, config={"handDrawnSeed": 1}, engine=backend).svg()
    # One pixel of slack: mmdc 12 renders with Chrome's own text layout (font sizes snapped to its grid, tspan runs
    # placed on LayoutUnits), and the shim deliberately doesn't hand-round to copy that.
    diffs = sc.compare(sc.parse(sc.mask_random_ids(ours)), sc.parse(sc.mask_random_ids(ref)), abs_tol=1.0)
    assert not diffs, f"{len(diffs)} differences, first:\n" + "\n".join(diffs[:5])


@pytest.mark.parametrize("name", ["06_complex_sequence", "38_class_advanced", "01_simple_flowchart"])
def test_rendering_twice_gives_the_same_bytes(name):
    """mmdc opens a fresh page per diagram, so mermaid.js's id counters (actor1, classId-Animal-0, ...) always
    start from zero. Each mermaidx render must start from the same state, whatever was rendered before."""
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    first = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    second = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()
    assert first == second
