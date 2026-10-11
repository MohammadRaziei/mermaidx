"""`getBBox()` of an SVG <path>, checked against what Chrome returned for every distinct `d`
in tests/samples (tests/data/chrome_path_bbox.json, made with Chrome 153). Chrome keeps path geometry in
float32 (Skia), so the comparison is exact: bit for bit, after rounding our doubles to float32.

A handful of paths still end one float32 step away from Chrome (cause not found: an arc/cubic evaluated
with a last-bit different sinf/tanf/FMA is the suspect, unconfirmed). They are listed in
tests/data/path_bbox_known_ulp_off.json; the set must stay exactly that list -- a new mismatch fails, and so
does one of them getting fixed (remove it from the list then)."""
import json
import pathlib
import struct

import pytest
import quickjs

from mermaidx.path_bbox import PATH_BBOX_JS

_DATA_DIR = pathlib.Path(__file__).parent / "data"
_DATA = json.loads((_DATA_DIR / "chrome_path_bbox.json").read_text())["paths"]
_KNOWN_OFF = set(json.loads((_DATA_DIR / "path_bbox_known_ulp_off.json").read_text()))


def _f32(v: float) -> float:
    return struct.unpack("f", struct.pack("f", v))[0]


def _ulp(v: float) -> float:
    """Distance from |v| to the next float32 up."""
    bits = struct.unpack("I", struct.pack("f", abs(v)))[0]
    return struct.unpack("f", struct.pack("I", bits + 1))[0] - abs(v)


@pytest.fixture(scope="module")
def ours():
    ctx = quickjs.Context()
    ctx.eval(PATH_BBOX_JS)
    ds = json.dumps([p["d"] for p in _DATA])
    raw = ctx.eval(f"JSON.stringify({ds}.map(d => {{ const b = __pathBBox(d); return [b.x, b.y, b.width, b.height]; }}))")
    return [[_f32(v) for v in row] for row in json.loads(raw)]


def test_paths_match_chrome_exactly_except_the_known_ones(ours):
    differing = {p["d"] for p, o in zip(_DATA, ours) if o != p["bbox"]}
    assert differing == _KNOWN_OFF, (
        f"new mismatches: {[d[:60] for d in differing - _KNOWN_OFF]}; "
        f"fixed (remove from the list): {[d[:60] for d in _KNOWN_OFF - differing]}")


def test_the_known_ones_are_one_float32_step_away(ours):
    """A coordinate may be one step off; width/height are differences of two coordinates, so they get that
    step plus the rounding of the difference itself."""
    for p, o in zip(_DATA, ours):
        if p["d"] not in _KNOWN_OFF:
            continue
        x, y, w, h = p["bbox"]
        allowed = [_ulp(x), _ulp(y),
                   _ulp(max(abs(x), abs(x + w))) + _ulp(w), _ulp(max(abs(y), abs(y + h))) + _ulp(h)]
        for mine, chrome, tolerance in zip(o, p["bbox"], allowed):
            assert abs(mine - chrome) <= tolerance, (p["d"][:60], o, p["bbox"])


@pytest.mark.parametrize("d, expected", [
    ("", [0, 0, 0, 0]),
    ("M 10 20", [10, 20, 0, 0]),
    ("M 0 0 L 10 5 H 3 V -2 Z", [0, -2, 10, 7]),
    ("M 0 0 Q 5 10 10 0", [0, 0, 10, 5]),
])
def test_simple_paths(d, expected):
    ctx = quickjs.Context()
    ctx.eval(PATH_BBOX_JS)
    b = json.loads(ctx.eval(f"JSON.stringify(__pathBBox({json.dumps(d)}))"))
    assert [b["x"], b["y"], b["width"], b["height"]] == expected
