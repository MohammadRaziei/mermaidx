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


# ---------------------------------------------------------------------------
# URL polyfill (issue #25: "ReferenceError: URL is not defined" when a
# diagram uses `click node "https://..."` link handlers). QuickJS has no
# built-in URL; mermaid's click-href sanitizer calls `URL.canParse()` and
# `new URL(...).toString()` for absolute http(s) links.
# ---------------------------------------------------------------------------


def test_url_polyfill_parses_https_url_parts():
    ctx = _make_ctx()
    js = """
    const u = new URL("https://Example.COM:8080/a/b?x=1#frag");
    JSON.stringify({
      protocol: u.protocol, hostname: u.hostname, port: u.port,
      pathname: u.pathname, search: u.search, hash: u.hash, host: u.host,
    });
    """
    parts = json.loads(ctx.eval(js))
    assert parts == {
        "protocol": "https:",
        "hostname": "Example.COM",
        "port": "8080",
        "pathname": "/a/b",
        "search": "?x=1",
        "hash": "#frag",
        "host": "Example.COM:8080",
    }


def test_url_polyfill_lowercase_roundtrip_matches_mermaid_usage():
    """Mirrors exactly what mermaid's sanitize-url helper does: lower-case
    protocol and hostname in place, then stringify."""
    ctx = _make_ctx()
    js = """
    const u = new URL("HTTPS://Example.COM/path");
    u.protocol = u.protocol.toLowerCase();
    u.hostname = u.hostname.toLowerCase();
    u.toString();
    """
    assert ctx.eval(js) == "https://example.com/path"


def test_url_canparse_true_for_valid_and_false_for_invalid():
    ctx = _make_ctx()
    assert ctx.eval('URL.canParse("https://example.com")') is True
    assert ctx.eval('URL.canParse("not a url at all ::: %%")') is False


# ---------------------------------------------------------------------------
# Node.compareDocumentPosition (issue #24: "TypeError: not a function" while
# rendering a sankey diagram). d3 selection's .order() -- used to reorder
# sankey's <g> layers so links draw under/over nodes correctly -- calls
# node.compareDocumentPosition(otherNode) directly.
# ---------------------------------------------------------------------------


def test_compare_document_position_siblings():
    ctx = _make_ctx()
    js = """
    const parent = document.createElement("g");
    const a = document.createElement("rect");
    const b = document.createElement("rect");
    parent.appendChild(a);
    parent.appendChild(b);
    JSON.stringify({
      aFollowsB: !!(b.compareDocumentPosition(a) & 4),
      bFollowsA: !!(a.compareDocumentPosition(b) & 4),
      aPrecedesB: !!(a.compareDocumentPosition(b) & 2) === false,
    });
    """
    result = json.loads(ctx.eval(js))
    # a comes before b in document order, so from b's perspective a PRECEDES
    # (bit 2), and from a's perspective b FOLLOWS (bit 4).
    assert result["bFollowsA"] is True
    assert result["aFollowsB"] is False


def test_compare_document_position_ancestor_descendant():
    ctx = _make_ctx()
    js = """
    const parent = document.createElement("g");
    const child = document.createElement("rect");
    parent.appendChild(child);
    JSON.stringify({
      childContainedByParent: !!(parent.compareDocumentPosition(child) & 16),
      parentContainsChild: !!(child.compareDocumentPosition(parent) & 8),
    });
    """
    result = json.loads(ctx.eval(js))
    assert result["childContainedByParent"] is True
    assert result["parentContainsChild"] is True


def test_compare_document_position_same_node_and_disconnected():
    ctx = _make_ctx()
    js = """
    const a = document.createElement("rect");
    const b = document.createElement("rect");  // never attached anywhere
    JSON.stringify({
      same: a.compareDocumentPosition(a),
      disconnected: !!(a.compareDocumentPosition(b) & 1),
    });
    """
    result = json.loads(ctx.eval(js))
    assert result["same"] == 0
    assert result["disconnected"] is True


# ---------------------------------------------------------------------------
# CSS.supports("color", value) polyfill (issue #27: "ReferenceError: Option
# is not defined" when a sequenceDiagram uses `box <color> ...` groups).
# mermaid's box-color parser tries `window.CSS.supports("color", name)`
# first and only falls back to a `new Option().style.color = ...` browser
# trick when `CSS` is missing -- QuickJS has neither, so it always hit that
# unimplementable fallback.
# ---------------------------------------------------------------------------


def test_css_supports_color_named_colors():
    ctx = _make_ctx()
    assert ctx.eval('CSS.supports("color", "Purple")') is True
    assert ctx.eval('CSS.supports("color", "rebeccapurple")') is True
    assert ctx.eval('CSS.supports("color", "transparent")') is True


def test_css_supports_color_hex_and_functions():
    ctx = _make_ctx()
    assert ctx.eval('CSS.supports("color", "#ff00aa")') is True
    assert ctx.eval('CSS.supports("color", "#f0a")') is True
    assert ctx.eval('CSS.supports("color", "rgb(10, 20, 30)")') is True
    assert ctx.eval('CSS.supports("color", "hsla(200, 50%, 50%, 0.5)")') is True


def test_css_supports_color_rejects_non_colors():
    ctx = _make_ctx()
    assert ctx.eval('CSS.supports("color", "Alice")') is False
    assert ctx.eval('CSS.supports("color", "not-a-color-at-all")') is False


def test_css_supports_only_checks_color_property():
    """mermaid only ever calls this with prop="color"; other properties
    should just report unsupported rather than crash."""
    ctx = _make_ctx()
    assert ctx.eval('CSS.supports("display", "flex")') is False


# ---------------------------------------------------------------------------
# Node.previousSibling (issue #27, follow-up: the box-color crash was fixed
# by the CSS.supports polyfill above, but the box then rendered as an
# opaque rect covering the whole diagram. Root cause: mermaid calls d3
# selection's .lower() on the box's <g> to push it behind the actors/
# messages appended after it; .lower() is
# `this.previousSibling && this.parentNode.insertBefore(this, this.parentNode.firstChild)`
# -- and previousSibling was simply missing from Node, so it silently
# no-opped instead of throwing.
# ---------------------------------------------------------------------------


def test_previous_sibling_basic():
    ctx = _make_ctx()
    js = """
    const parent = document.createElement("g");
    const a = document.createElement("rect");
    const b = document.createElement("rect");
    const c = document.createElement("rect");
    parent.appendChild(a);
    parent.appendChild(b);
    parent.appendChild(c);
    JSON.stringify({
      aPrev: a.previousSibling === null,
      bPrev: b.previousSibling === a,
      cPrev: c.previousSibling === b,
    });
    """
    result = json.loads(ctx.eval(js))
    assert result == {"aPrev": True, "bPrev": True, "cPrev": True}


def test_previous_sibling_matches_d3_lower_pattern():
    """Reproduces d3's actual .lower() body against the shim directly:
    a node with no previousSibling is left alone; a node with one gets
    moved to be the parent's first child."""
    ctx = _make_ctx()
    js = """
    function lower(node) {
      if (node.previousSibling) node.parentNode.insertBefore(node, node.parentNode.firstChild);
    }
    const parent = document.createElement("g");
    const a = document.createElement("rect");
    const b = document.createElement("rect");
    const c = document.createElement("rect");
    parent.appendChild(a);
    parent.appendChild(b);
    parent.appendChild(c);
    lower(c);  // c had siblings before it -> should become the first child
    JSON.stringify(parent.childNodes.map(n => n === a ? "a" : n === b ? "b" : "c"));
    """
    assert json.loads(ctx.eval(js)) == ["c", "a", "b"]


# ---------------------------------------------------------------------------
# Node.toJSON() (issue #23: "TypeError: circular reference" rendering a
# block diagram). Some diagrams stash a live d3 selection wrapping a DOM
# node inside a plain data object that later gets JSON.stringify'd for a
# debug-log line. In a real browser, Node.prototype.parentNode/childNodes
# are non-enumerable prototype getters, so JSON.stringify(element) just
# serializes to "{}"; here they're own enumerable instance properties (so
# the rest of the shim can read/write them directly), which without
# toJSON() makes JSON.stringify walk the whole parent<->child graph and
# hit a genuine cycle.
# ---------------------------------------------------------------------------


def test_json_stringify_element_does_not_throw():
    ctx = _make_ctx()
    js = """
    const parent = document.createElement("g");
    const child = document.createElement("rect");
    parent.appendChild(child);
    JSON.stringify(child);  // used to throw: "TypeError: circular reference"
    """
    assert ctx.eval(js) == "{}"


def test_json_stringify_object_containing_a_node_does_not_throw():
    """Matches the actual failure shape from issue #23: a plain object
    (like block layout's `size`) holding a reference to a live node."""
    ctx = _make_ctx()
    js = """
    const el = document.createElement("rect");
    const size = { width: 10, height: 20, x: 0, y: 0, node: el };
    JSON.stringify(size);
    """
    result = json.loads(ctx.eval(js))
    assert result == {"width": 10, "height": 20, "x": 0, "y": 0, "node": {}}