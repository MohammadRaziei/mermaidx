"""getBBox of the basic shapes against Chrome: how it reads their length attributes.

tests/data/chrome_shape_bbox.json holds, for each piece of markup, the box Chrome 153 gave for its first
element (@sparticuz/chromium through Playwright; only the source of the numbers, not a dependency). Each shape sits
in a <g style="font-size: 20px"> inside a 400x300 <svg>, which has viewBox="0 0 200 100" where a case says so.

What it pins down: units (px, pt, pc, mm, cm, in, em, ex, rem, %), a unit is case-insensitive, an invalid or
negative size is 0, and every number is a float32.
"""
import json
import pathlib

import pytest

from mermaidx.engines.quickjs_engine import Engine

_CASES = json.loads((pathlib.Path(__file__).parent / "data" / "chrome_shape_bbox.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def engine():
    e = Engine()
    e.start()
    yield e
    e.close()


def _bbox(engine, case):
    js = f"""(() => {{
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(NS, "svg");
        svg.setAttribute("width", "400");
        svg.setAttribute("height", "300");
        {('svg.setAttribute("viewBox", ' + json.dumps(case["viewBox"]) + ');') if "viewBox" in case else ""}
        document.body.appendChild(svg);
        const g = document.createElementNS(NS, "g");
        g.setAttribute("style", "font-size: 20px");
        svg.appendChild(g);
        g.innerHTML = {json.dumps(case["markup"])};
        const b = g.childNodes[0].getBBox();
        document.body.removeChild(svg);
        return JSON.stringify([b.x, b.y, b.width, b.height]);
    }})()"""
    return json.loads(engine._executor.submit(engine._ctx.eval, js).result())


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_shape_bbox_matches_chrome(engine, case):
    assert _bbox(engine, case) == pytest.approx(case["bbox"], abs=1e-4)


def test_lengths_are_float32_before_they_are_subtracted(engine):
    """cx=13.629pt, r=1.782pt: the box's x is float32(cx) - float32(r), not float32 of the exact difference. They
    are 2e-6 apart, below the tolerance above, so this one is compared exactly."""
    case = next(c for c in _CASES if c["name"] == "circle pt arithmetic")
    assert _bbox(engine, case) == case["bbox"]
