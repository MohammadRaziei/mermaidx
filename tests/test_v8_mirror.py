"""The JS mirror of the text measurer that V8 runs (V8 cannot call back into Python synchronously) must give
exactly what the Python measurer gives quickjs: the same width, ascent, descent and x-height, and the same glyph
boxes for the ink rule of a <text> box. Compared on text that is hard for it: kerning, non-ASCII, glyphs the
font does not have."""
import json

import pytest

from mermaidx.font_metrics import get_font

mini_racer = pytest.importorskip("py_mini_racer")

_TEXTS = [
    "", " ", "Hello", "AVATAR To Wa", "fi fl ffi", "HTTP POST /render", "Ty. Vo, Yo; P.A.", "Lorem ipsum dolor sit amet, consectetur",
    "héllo wörld", "Привет мир", "Καλημέρα", "ÀÉÎÕÜ ÅØ ß", "AV́ T̂o", "→ ← ↔ ✓ ✗ ≤ ≥", "日本語 中文", "\U0001F600 emoji", "\U0010FFFF",
    "tab\tand\nnewline", "a  b   c", "1,234.56 %", "<b>x</b> & y",
]
_SIZES = [9, 12, 14, 16, 19.5, 38]
_WEIGHTS = [None, "normal", "400", "bold", "700", "600", "bolder"]


@pytest.fixture(scope="module")
def ctx():
    from mermaidx.engines.v8_engine import _measure_text_js

    c = mini_racer.MiniRacer()
    c.eval("globalThis.__log = (s) => {};")
    c.eval(_measure_text_js())
    return c


def _same_boxes(got, want, label):
    assert len(got) == len(want), (label, got, want)
    for g, w in zip(got, want):
        assert g == pytest.approx(list(w), abs=1e-9), label


def _js(ctx, fn, *args):
    return json.loads(ctx.eval(f"JSON.stringify({fn}(...{json.dumps(list(args))}))"))


@pytest.mark.parametrize("weight", _WEIGHTS)
@pytest.mark.parametrize("size", _SIZES)
def test_measure_matches_python(ctx, size, weight):
    for text in _TEXTS:
        want = get_font(weight).measure(text, float(size))
        got = _js(ctx, "__measureTextFull", text, size, "sans-serif", weight, "normal")
        for key in ("width", "ascent", "descent", "xHeight"):
            assert got[key] == pytest.approx(want[key], abs=1e-9), (text, key)


@pytest.mark.parametrize("weight", _WEIGHTS)
@pytest.mark.parametrize("size", _SIZES)
def test_glyph_boxes_match_python(ctx, size, weight):
    for text in _TEXTS:
        want = get_font(weight).glyph_boxes(text, float(size))
        got = _js(ctx, "__measureGlyphs", text, size, "sans-serif", weight, "normal")
        _same_boxes(got, want, text)


def _all_strings(alphabet, max_len):
    out, layer = [""], [""]
    for _ in range(max_len):
        layer = [s + c for s in layer for c in alphabet]
        out += layer
    return out


@pytest.mark.parametrize("weight", [None, "bold"])
def test_every_short_string_over_the_ligature_letters_matches_python(ctx, weight):
    """f, i, l, a space and a letter that starts nothing: every string up to length 5 -- ff, fi, fl, ffi, ffl in
    every context, a ligature next to another one, and the near misses (f i, fb, ffa)."""
    texts = _all_strings(["f", "i", "l", " ", "A"], 5)
    js = ctx.eval(
        f"""JSON.stringify({json.dumps(texts)}.map((t) => {{
            const m = __measureTextFull(t, 16, "x", {json.dumps(weight)}, "normal");
            return [m.width, __measureGlyphs(t, 16, "x", {json.dumps(weight)}, "normal")];
        }}))"""
    )
    got = json.loads(js)
    font = get_font(weight)
    for text, (width, glyphs) in zip(texts, got):
        assert width == pytest.approx(font.measure(text, 16.0)["width"], abs=1e-9), text
        _same_boxes(glyphs, font.glyph_boxes(text, 16.0), text)
