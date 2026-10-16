"""getBBox of <text> against Chrome, with the real font (DejaVu Sans) measured by novasvg.

tests/data/chrome_text_bbox.json holds, for each piece of markup, the box Chrome 153 gave for its <text>
(@sparticuz/chromium through Playwright, fontconfig mapping every family to DejaVu Sans). Chrome is only the
source of those numbers: it is not a dependency of the package or of this test.

The tolerance is the one tests/test_mmdc_structural.py uses: Chrome rounds the width of every text run up to
1/64 px (LayoutUnit) and adds them; the shim rounds the sum.
"""
import json
import pathlib

import pytest

from mermaidx.engines.quickjs_engine import Engine

_CASES = json.loads((pathlib.Path(__file__).parent / "data" / "chrome_text_bbox.json").read_text(encoding="utf-8"))
_TOLERANCE = 0.02


@pytest.fixture(scope="module")
def engine():
    e = Engine()
    e.start()
    yield e
    e.close()


def _bbox(engine, markup):
    js = f"""(() => {{
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(NS, "svg");
        document.body.appendChild(svg);
        const g = document.createElementNS(NS, "g");
        svg.appendChild(g);
        g.innerHTML = {json.dumps(markup)};
        const b = g.querySelector("text").getBBox();
        document.body.removeChild(svg);
        return JSON.stringify([b.x, b.y, b.width, b.height]);
    }})()"""
    return json.loads(engine._executor.submit(engine._ctx.eval, js).result())


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_text_bbox_matches_chrome(engine, case):
    assert _bbox(engine, case["markup"]) == pytest.approx(case["bbox"], abs=_TOLERANCE)
