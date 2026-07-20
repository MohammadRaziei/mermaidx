"""Direct unit tests for mermaidx/assets/dom_shim.js's text-position
helpers (__resolveTextPos / __accumulatePos / __computeBBox), isolated
from full mermaid.js diagram rendering.

These load *only* the DOM shim (not mermaid.js itself) into a bare
QuickJS context and build small hand-crafted element trees that mirror
the exact shapes mermaid.js emits for text labels:

    single line, one word:
        <text y="-10.1">
          <tspan class="text-outer-tspan row" x="0" y="-0.1em" dy="1.1em">Hello</tspan>
        </text>

    single line, multiple words (mermaid wraps each word in its own
    inner tspan, but they all share the row's y/dy):
        <text y="-10.1">
          <tspan class="text-outer-tspan row" x="0" y="-0.1em" dy="1.1em">
            <tspan class="text-inner-tspan">Two</tspan>
            <tspan class="text-inner-tspan"> words</tspan>
          </tspan>
        </text>

    multi-line (one row tspan per visual line):
        <text y="-10.1">
          <tspan class="text-outer-tspan row" x="0" y="-0.1em" dy="1.1em">Two line</tspan>
          <tspan class="text-outer-tspan row" x="0" y="1em"   dy="1.1em">edge comment</tspan>
        </text>

This purpose-built harness is what lets these tests assert the exact
resolved (x, y, width, height) rather than just "did it crash" -- and,
critically, it pins down that __resolveTextPos's chain-walking refactor
(splitting it into __chainTo + __accumulatePos so multi-line labels could
reuse the accumulation logic against the first row) did not change the
result for ordinary single-line labels, which is the shape the vast
majority of diagrams use.

A fixed, deterministic fake text measurer is used (width = len(text) *
size * 0.5, ascent = size * 0.8, descent = size * 0.2) so expected
numbers can be hand-computed and asserted exactly, rather than depending
on the real bundled font.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

quickjs = pytest.importorskip("quickjs")

_DOM_SHIM_JS = (
    Path(__file__).parent.parent / "mermaidx" / "assets" / "dom_shim.js"
).read_text(encoding="utf-8")

FONT_SIZE = 16  # matches mermaid's default flowchart label font-size


def _make_ctx():
    """A bare QuickJS context with only the DOM shim loaded (no mermaid.js)
    and a deterministic fake text measurer wired in."""
    ctx = quickjs.Context()
    ctx.add_callable("__log_raw", lambda s: None)
    ctx.add_callable(
        "__measureText_raw", lambda t, s, f, w, st: len(t or "") * s * 0.5
    )
    ctx.add_callable(
        "__measureTextFull_raw",
        lambda t, s, f, w, st: json.dumps(
            {"width": len(t or "") * s * 0.5, "ascent": s * 0.8, "descent": s * 0.2}
        ),
    )
    ctx.eval(
        "globalThis.__log = (s) => __log_raw(s);\n"
        "globalThis.__measureText = (t,s,f,w,st) => __measureText_raw(t,s,f,w,st);\n"
        "globalThis.__measureTextFull = (t,s,f,w,st) => "
        "JSON.parse(__measureTextFull_raw(t,s,f,w,st));\n"
    )
    ctx.eval(_DOM_SHIM_JS)
    return ctx


def _bbox_single_word():
    ctx = _make_ctx()
    js = """
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("y", "-10.1");
    const row = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    row.setAttribute("class", "text-outer-tspan row");
    row.setAttribute("x", "0");
    row.setAttribute("y", "-0.1em");
    row.setAttribute("dy", "1.1em");
    row.textContent = "Hello";
    el.appendChild(row);
    JSON.stringify(el.getBBox());
    """
    return json.loads(ctx.eval(js))


def _bbox_multi_word_single_line():
    ctx = _make_ctx()
    js = """
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("y", "-10.1");
    const row = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    row.setAttribute("class", "text-outer-tspan row");
    row.setAttribute("x", "0");
    row.setAttribute("y", "-0.1em");
    row.setAttribute("dy", "1.1em");
    const w1 = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    w1.setAttribute("class", "text-inner-tspan");
    w1.textContent = "Two";
    const w2 = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    w2.setAttribute("class", "text-inner-tspan");
    w2.textContent = " words";
    row.appendChild(w1);
    row.appendChild(w2);
    el.appendChild(row);
    JSON.stringify(el.getBBox());
    """
    return json.loads(ctx.eval(js))


def _bbox_two_lines():
    ctx = _make_ctx()
    js = """
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("y", "-10.1");
    function row(y, dy, text) {
      const r = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
      r.setAttribute("class", "text-outer-tspan row");
      r.setAttribute("x", "0");
      r.setAttribute("y", y);
      r.setAttribute("dy", dy);
      r.textContent = text;
      return r;
    }
    el.appendChild(row("-0.1em", "1.1em", "Two line"));
    el.appendChild(row("1em", "1.1em", "edge comment"));
    JSON.stringify(el.getBBox());
    """
    return json.loads(ctx.eval(js))


def test_single_word_line_bbox_matches_hand_computed_position():
    """Baseline single-tspan case: the outer <text>'s own y="-10.1" must be
    fully overridden by the row tspan's y="-0.1em" dy="1.1em" (real SVG
    semantics: an explicit y on a descendant resets position), giving
    pos.y = (-0.1 + 1.1) * FONT_SIZE = 1.0 * FONT_SIZE, and
    bbox.y = pos.y - ascent."""
    bbox = _bbox_single_word()
    ascent = FONT_SIZE * 0.8
    expected_y = (1.0 * FONT_SIZE) - ascent
    assert bbox["y"] == pytest.approx(expected_y)
    assert bbox["x"] == 0
    assert bbox["width"] == pytest.approx(len("Hello") * FONT_SIZE * 0.5)
    assert bbox["height"] == pytest.approx(FONT_SIZE)  # ascent + descent


def test_multi_word_single_line_matches_single_word_case():
    """Splitting one line across several inner word-tspans (as mermaid does
    for styled runs) must not change the resolved y at all -- the chain
    still stops at the row tspan itself, since only *it* carries y/dy."""
    one_word = _bbox_single_word()
    multi_word = _bbox_multi_word_single_line()
    assert multi_word["y"] == pytest.approx(one_word["y"])
    assert multi_word["width"] == pytest.approx(len("Two words") * FONT_SIZE * 0.5)


def test_multiline_label_uses_first_row_not_outer_text_y():
    """Regression for issue #17. Before the fix, a label with >1 row tspan
    made __resolveTextPos's single-child-chain walk stop at the outer
    <text> element (which has 2+ children, one per line) and use its
    vestigial, non-"em" y="-10.1" verbatim -- instead of descending into
    the first row to read its real y="-0.1em" dy="1.1em" position.

    This asserts the multi-line bbox's top (bbox.y) is identical to the
    single-line case's -- i.e. adding a second line must only grow the
    box *downward* (taller height, same top), not shift where the first
    line's own top is computed to be.
    """
    single = _bbox_single_word()
    multi = _bbox_two_lines()
    assert multi["y"] == pytest.approx(single["y"]), (
        "adding a second line changed the resolved top of the first line -- "
        "the multi-line branch must resolve position via the first row, "
        "matching what a single-line label with the same first row would get"
    )
    # Width is the widest row ("edge comment", 12 chars), not both rows'
    # text concatenated together.
    assert multi["width"] == pytest.approx(len("edge comment") * FONT_SIZE * 0.5)
    # Height = one line box + one extra 1.1em line-step for the 2nd row.
    ascent, descent = FONT_SIZE * 0.8, FONT_SIZE * 0.2
    assert multi["height"] == pytest.approx((ascent + descent) + 1.1 * FONT_SIZE)