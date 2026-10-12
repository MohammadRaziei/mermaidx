"""The x-height of the font reaches the DOM shim (dominant-baseline: middle needs it) through both engines."""
import pytest

from mermaidx.font_metrics import get_font


@pytest.mark.parametrize("weight", ["normal", "bold"])
@pytest.mark.parametrize("size", [10, 12, 16, 38])
def test_measure_reports_the_x_height(weight, size):
    font = get_font(weight)
    assert font.measure("Section", size)["xHeight"] == font._at_size(size).x_height


@pytest.mark.parametrize("weight", ["normal", "bold"])
def test_metrics_summary_lets_a_js_engine_reproduce_it(weight):
    font = get_font(weight)
    summary = font.metrics_summary()
    for size in (10, 12, 16, 38):
        assert summary["xHeight"] * size / summary["unitsPerEm"] == pytest.approx(font._at_size(size).x_height, abs=1e-4)


# End to end: a treemap labels its sections with `dominant-baseline: middle`, so the diagram's size depends on
# the x-height reaching the shim. Both engines have to give the same document (up to measurement noise).
def test_both_engines_lay_out_baseline_dependent_text_alike():
    pytest.importorskip("py_mini_racer")
    import os
    import sys

    sys.path.insert(0, os.path.dirname(__file__))
    import svg_compare as sc
    import mermaidx

    src = open(os.path.join(os.path.dirname(__file__), "samples", "30_treemap.mmd"), encoding="utf-8").read()
    docs = {b: mermaidx.render(src, backend=b, config={"handDrawnSeed": 1}).svg() for b in ("quickjs", "v8")}
    assert "NaN" not in docs["v8"] and "NaN" not in docs["quickjs"]
    assert sc.compare(sc.parse(docs["quickjs"]), sc.parse(docs["v8"])) == []
