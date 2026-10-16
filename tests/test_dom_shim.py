"""Direct unit tests for mermaidx/assets/dom_shim.js's text-position
helpers (__layoutSvgText / __computeBBox), isolated
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
critically, it pins down that a multi-line label (one tspan per line) only
grows the box downward and leaves the first line where a single-line label
would put it.

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

_PATH_BBOX_JS = (
    Path(__file__).parent.parent / "mermaidx" / "assets" / "path_bbox.js"
).read_text(encoding="utf-8")

FONT_SIZE = 16  # matches mermaid's default flowchart label font-size


def _make_ctx(glyphs=None):
    """A bare QuickJS context with only the DOM shim loaded (no mermaid.js)
    and a deterministic fake text measurer wired in. `glyphs`, if given, is
    what the fake __measureGlyphs returns: [(pen, ink_left, ink_right, ink_top, ink_bottom), ...]."""
    ctx = quickjs.Context()
    ctx.add_callable("__log_raw", lambda s: None)
    ctx.add_callable(
        "__measureText_raw", lambda t, s, f, w, st: len(t or "") * s * 0.5
    )
    ctx.add_callable(
        "__measureTextFull_raw",
        lambda t, s, f, w, st: json.dumps(
            {"width": len(t or "") * s * 0.5, "ascent": s * 0.8, "descent": s * 0.2, "xHeight": s * 0.5}
        ),
    )
    ctx.eval(
        "globalThis.__log = (s) => __log_raw(s);\n"
        "globalThis.__measureText = (t,s,f,w,st) => __measureText_raw(t,s,f,w,st);\n"
        "globalThis.__measureTextFull = (t,s,f,w,st) => "
        "JSON.parse(__measureTextFull_raw(t,s,f,w,st));\n"
    )
    if glyphs is not None:
        ctx.add_callable("__measureGlyphs_raw", lambda t, s, f, w, st: json.dumps(glyphs))
        ctx.eval("globalThis.__measureGlyphs = (t,s,f,w,st) => JSON.parse(__measureGlyphs_raw(t,s,f,w,st));")
    ctx.eval(_PATH_BBOX_JS)  # the engines evaluate it before the shim, which calls __pathBBox / __parseSvgNumber
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
    # A browser sizes a text box from font metrics rounded to whole pixels, so
    # the stub's fractional ascent (0.8 * size) is rounded before use.
    ascent = round(FONT_SIZE * 0.8)
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
    """Regression for issue #17. A label with >1 row tspan once took the outer
    <text>'s vestigial, non-"em" y="-10.1" as its position, instead of the
    first row's real y="-0.1em" dy="1.1em".

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
    ascent, descent = round(FONT_SIZE * 0.8), round(FONT_SIZE * 0.2)  # whole-pixel metrics, as a browser
    assert multi["height"] == pytest.approx((ascent + descent) + 1.1 * FONT_SIZE)


# ---------------------------------------------------------------------------
# URL polyfill (issue #25: "ReferenceError: URL is not defined" when a
# diagram uses `click node "https://..."` link handlers). QuickJS has no
# built-in URL; mermaid's click-href sanitizer calls `URL.canParse()` and
# `new URL(...).toString()` for absolute http(s) links.
# ---------------------------------------------------------------------------


# --- Chrome's ink-bounds rule for an SVG <text> box ---------------------------------------------
# The fake measurer gives "abc" at 16px an advance of 3 * 16 * 0.5 = 24. Chrome's getBBox() is the
# union of the advance box [0, 24] with every glyph's ink box rounded OUT to whole pixels relative
# to the glyph's own pen position (see __inkExtent in dom_shim.js).

def _text_bbox(glyphs, anchor=None, x=10):
    # horizontal-only cases: keep the ink vertically inside the font's [-13, 3] box at 16px
    glyphs = glyphs and [g + [-5, 2] if len(g) == 3 else g for g in glyphs]
    ctx = _make_ctx(glyphs)
    attrs = f'el.setAttribute("text-anchor", "{anchor}");' if anchor else ""
    return json.loads(ctx.eval(f"""
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("x", "{x}"); el.setAttribute("y", "20"); {attrs}
    el.textContent = "abc";
    JSON.stringify(el.getBBox());
    """))


def test_text_bbox_without_glyph_data_is_the_advance_box():
    assert _text_bbox(None)["width"] == 24 and _text_bbox(None)["x"] == 10


def test_text_bbox_ink_inside_the_advance_changes_nothing():
    box = _text_bbox([[0, 1.2, 9.8], [12, 1.0, 10.9]])  # 12 + ceil(10.9) = 23 < 24
    assert (box["x"], box["width"]) == (10, 24)


def test_text_bbox_ink_past_the_advance_grows_right_by_whole_pixels():
    # last glyph painted at pen 20 with ink up to 9.2 -> ceil = 10 -> right edge 30, not 24 or 29.2
    box = _text_bbox([[0, 1.0, 9.0], [20, 1.0, 9.2]])
    assert (box["x"], box["width"]) == (10, 20 + 10)


def test_text_bbox_negative_left_bearing_grows_left_by_whole_pixels():
    # ink starts 0.047px left of the pen -> floor = -1 -> box starts 1px early, x moves left by 1
    box = _text_bbox([[0, -0.047, 9.8]])
    assert (box["x"], box["width"]) == (10 - 1, 24 + 1)


def test_text_bbox_anchor_uses_the_advance_then_ink_offsets_apply():
    # text-anchor:middle shifts by half the ADVANCE (12); the ink left edge (-1) is added on top.
    box = _text_bbox([[0, -0.047, 9.8], [20, 1.0, 9.2]], anchor="middle", x=100)
    assert box["x"] == 100 - 12 - 1
    assert box["width"] == 30 + 1


def test_get_computed_text_length_stays_the_plain_advance():
    ctx = _make_ctx([[20, 1.0, 9.2]])
    assert ctx.eval('''
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.textContent = "abc"; el.getComputedTextLength();
    ''') == 24


def test_text_bbox_vertical_ink_grows_the_box_by_whole_pixels():
    # fake font at 16px: ascent 12.8 -> 13, descent 3.2 -> 3 (box is [-13, 3] around the baseline, y=20).
    plain = _text_bbox([[0, 1, 9, -5, 2]])
    assert (plain["y"], plain["height"]) == (20 - 13, 16)
    # a descender reaching 3.4 below the baseline -> ceil = 4: one pixel taller at the bottom
    desc = _text_bbox([[0, 1, 9, -5, 3.4]])
    assert (desc["y"], desc["height"]) == (20 - 13, 17)
    # an ascender reaching 13.2 above -> floor(-13.2) = -14: one pixel taller at the top
    asc = _text_bbox([[0, 1, 9, -13.2, 2]])
    assert (asc["y"], asc["height"]) == (20 - 14, 17)


def test_element_id_reflects_the_attribute():
    # mermaid clones a marker and renames the clone with `clone.id = ...`
    ctx = _make_ctx()
    assert ctx.eval('''
    const a = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    a.setAttribute("id", "m1");
    const b = a.cloneNode(true);
    b.id = "m1_red";
    [a.id, b.id, b.getAttribute("id"), a.getAttribute("id")].join("|");
    ''') == "m1|m1_red|m1_red|m1"


def test_stylesheet_rules_are_serialized_like_the_cssom():
    ctx = _make_ctx()
    out = json.loads(ctx.eval('''
    const sheet = new CSSStyleSheet();
    sheet.insertRule(".good > * { fill:#d4edda !important; stroke-dasharray: 5 5 !important; stroke-width:2px }", 0);
    sheet.insertRule(':root { --mermaid-font-family: "trebuchet ms",verdana }', 1);
    sheet.insertRule("@media print { a { color: red } }", 2);
    JSON.stringify(sheet.cssRules.map((r) => r.cssText));
    '''))
    assert out[0] == ".good > * { fill: rgb(212, 237, 218) !important; stroke-dasharray: 5, 5 !important; stroke-width: 2px; }"
    assert out[1] == ':root { --mermaid-font-family: "trebuchet ms",verdana; }'  # custom properties stay verbatim
    assert out[2] == "@media print { a { color: red } }"                         # at-rules are left alone


def test_stylesheet_replace_sync_makes_one_rule_per_block():
    ctx = _make_ctx()
    assert json.loads(ctx.eval('''
    const s = new CSSStyleSheet();
    s.replaceSync(".a{color:#fff} .b{margin:0}");
    JSON.stringify(s.cssRules.map((r) => r.cssText));
    ''')) == [".a { color: rgb(255, 255, 255); }", ".b { margin: 0; }"]


def test_style_attribute_values_are_canonicalized_once_the_cssom_rewrites_the_block():
    ctx = _make_ctx()
    # setAttribute alone stays verbatim; a later CSSOM write re-serializes the whole block canonically
    assert ctx.eval('''
    const d = document.createElement("div");
    d.setAttribute("style", "color:#155724 !important");
    d.outerHTML;
    ''').count("#155724") == 1
    assert "color: rgb(21, 87, 36) !important; display: table-cell;" in ctx.eval('''
    const e = document.createElement("div");
    e.setAttribute("style", "color:#155724 !important");
    e.style.setProperty("display", "table-cell");
    e.outerHTML;
    ''')


def _group_bbox(transform):
    ctx = _make_ctx()
    return json.loads(ctx.eval(f'''
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    r.setAttribute("width", "10"); r.setAttribute("height", "20");
    r.setAttribute("transform", "{transform}");
    g.appendChild(r);
    JSON.stringify(g.getBBox());
    '''))


def test_group_bbox_maps_children_through_the_whole_transform_list():
    assert _group_bbox("translate(5 7)") == {"x": 5, "y": 7, "width": 10, "height": 20}
    box = _group_bbox("rotate(90)")  # (x, y) -> (-y, x): the 10x20 box becomes 20x10 at x=-20
    assert (box["x"], box["y"], box["width"], box["height"]) == (-20, 0, 20, 10)
    box = _group_bbox("translate(100 0) scale(2 3)")
    assert (box["x"], box["y"], box["width"], box["height"]) == (100, 0, 20, 60)
    # rotation about a centre: 90deg around (5,10) keeps the 10x20 box's centre and swaps its sides
    box = _group_bbox("rotate(90, 5, 10)")
    assert (round(box["x"], 6), round(box["y"], 6), round(box["width"], 6), round(box["height"], 6)) == (-5, 5, 20, 10)


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

# -- SVG lengths are float32 -------------------------------------------------------------------------------
# Blink stores an SVGLength as a float, parsed by the same number parser as path data. A coordinate such as
# y="8.855451867927453" is 8.855451583862305 by the time anything is subtracted from it (a sankey label's bbox
# top is that y minus the ascent: 1 float32 step apart depending on which of the two is rounded first).

def test_svg_length_is_parsed_to_float32():
    ctx = _make_ctx()
    assert ctx.eval(
        'const el = document.createElementNS("http://www.w3.org/2000/svg", "text");'
        'el.setAttribute("y", "8.855451867927453");'
        '__svgLength(el, "y") === Math.fround(8.855451867927453)'
    )


def test_em_length_is_a_float32_product():
    ctx = _make_ctx()
    assert ctx.eval(
        'const el = document.createElementNS("http://www.w3.org/2000/svg", "text");'
        'el.setAttribute("style", "font-size: 14px"); el.setAttribute("dy", "1.1em");'
        '__svgLength(el, "dy") === Math.fround(Math.fround(1.1) * 14)'
    )


def test_dy_is_added_in_float32():
    """Blink keeps x/y/dx/dy as float32, so y + dy is rounded to float32 before anything is built on it.
    (13 is the fake measurer's ascent at 16px: the box's top is that far above the baseline.)"""
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("y", "8.855451867927453");
        t.setAttribute("dy", "0.3");
        t.textContent = "a";
        t.getBBox().y === Math.fround(Math.fround(Math.fround(8.855451867927453) + Math.fround(0.3)) - 13);
        """
    )
    assert got


# -- a CSSOM write that changes nothing leaves the style attribute as written ---------------------------------
# Chrome (probed): style="...font-size: 38px;fill:#ffffff;" stays byte for byte after
# el.style.setProperty("font-size", "38px") -- the value is the one already in effect, so nothing is
# invalidated and the attribute is not rewritten. Equal means equal once parsed: "rgb(255, 255, 255)" is
# "#ffffff". A different value, a different priority or a new property rewrites the whole attribute.
_RAW_STYLE = "text-anchor: middle; font-size: 38px;fill:#ffffff;"


def _style_after(js_statement: str) -> str:
    ctx = _make_ctx()
    return ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
        el.setAttribute("style", {_RAW_STYLE!r});
        {js_statement};
        new XMLSerializer().serializeToString(el).match(/style="([^"]*)"/)[1];
        """
    )


@pytest.mark.parametrize("statement", [
    'el.style.setProperty("font-size", "38px")',
    "el.style.fontSize = '38px'",
    'el.style.setProperty("fill", "#ffffff")',
    'el.style.setProperty("fill", "rgb(255, 255, 255)")',
    'el.style.setProperty("stroke", null)',
    'el.style.removeProperty("stroke")',
])
def test_a_write_that_changes_nothing_keeps_the_attribute_verbatim(statement):
    assert _style_after(statement) == _RAW_STYLE


@pytest.mark.parametrize("statement, expected", [
    ('el.style.setProperty("font-size", "20px")',
     "text-anchor: middle; font-size: 20px; fill: rgb(255, 255, 255);"),
    ('el.style.setProperty("font-size", "38px", "important")',
     "text-anchor: middle; font-size: 38px !important; fill: rgb(255, 255, 255);"),
    ('el.style.setProperty("stroke", "red")',
     "text-anchor: middle; font-size: 38px; fill: rgb(255, 255, 255); stroke: red;"),
])
def test_a_write_that_changes_something_rewrites_the_whole_attribute(statement, expected):
    assert _style_after(statement) == expected


def test_a_value_written_twice_is_still_rewritten():
    assert _style_after('el.style.setProperty("font-size", "20px"); el.style.setProperty("font-size", "20px")') == \
        "text-anchor: middle; font-size: 20px; fill: rgb(255, 255, 255);"


# -- getBBox() ignores what is not rendered ------------------------------------------------------------------
# Probed in Chrome 153: a `display: none` child (style or attribute), or a group of them, is left out of its
# group's bbox; `visibility: hidden` is not (it still takes room); an element that is itself `display: none`
# has the empty bbox. mermaid hides labels that do not fit this way and then sizes the svg from getBBox().
def _bbox(build: str):
    ctx = _make_ctx()
    return ctx.eval(
        f"""
        const NS = "http://www.w3.org/2000/svg";
        const mk = (tag, attrs, parent) => {{
          const e = document.createElementNS(NS, tag);
          for (const k in attrs) e.setAttribute(k, attrs[k]);
          if (parent) parent.appendChild(e);
          return e;
        }};
        const b = ({build})(mk);
        JSON.stringify([b.x, b.y, b.width, b.height]);
        """
    )


_VISIBLE = '{x: 10, y: 10, width: 50, height: 20}'
_BIG = '{x: 0, y: 0, width: 100, height: 100}'


@pytest.mark.parametrize("hidden_child, expected", [
    (f"mk('rect', {{...{_BIG}, style: 'display: none;'}}, g)", "[10,10,50,20]"),
    (f"mk('rect', {{...{_BIG}, display: 'none'}}, g)", "[10,10,50,20]"),
    (f"mk('rect', {{...{_BIG}, style: 'visibility: hidden;'}}, g)", "[0,0,100,100]"),
    (f"mk('rect', {_BIG}, mk('g', {{style: 'display: none'}}, g))", "[10,10,50,20]"),
    (f"mk('rect', {{...{_BIG}, style: 'display: none'}}, g).style.setProperty('display', null)", "[0,0,100,100]"),
])
def test_group_bbox_skips_display_none_children(hidden_child, expected):
    assert _bbox(f"(mk) => {{ const g = mk('g', {{}}); mk('rect', {_VISIBLE}, g); {hidden_child}; return g.getBBox(); }}") == expected


def test_an_element_that_is_display_none_has_the_empty_bbox():
    assert _bbox("(mk) => mk('rect', {x: 5, y: 6, width: 7, height: 8, style: 'display: none'}).getBBox()") == "[0,0,0,0]"


@pytest.mark.parametrize("statement, expected", [
    ('el.style.removeProperty("fill")', "text-anchor: middle; font-size: 38px;"),
    ('el.style.setProperty("fill", null)', "text-anchor: middle; font-size: 38px;"),
    ('el.style.setProperty("fill", "")', "text-anchor: middle; font-size: 38px;"),
    ('el.style.removeProperty("fill"); el.style.setProperty("fill", "red")',
     "text-anchor: middle; font-size: 38px; fill: red;"),
])
def test_removing_a_declared_property_rewrites_the_attribute_without_it(statement, expected):
    assert _style_after(statement) == expected


def test_removing_the_only_declared_property_leaves_an_empty_style_attribute():
    ctx = _make_ctx()
    assert ctx.eval(
        """
        const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
        el.setAttribute("style", "fill:red");
        el.style.removeProperty("fill");
        new XMLSerializer().serializeToString(el).match(/style="([^"]*)"/)[1];
        """
    ) == ""


# -- dominant-baseline moves a text's box ----------------------------------------------------------------------
# Probed in Chrome 153 (DejaVu Sans, 7 sizes, normal and bold): the bbox keeps its size and moves down by
#   middle: xHeight/2   central: (ascent - descent)/2   mathematical: ascent/2   text-before-edge: ascent
#   text-after-edge, ideographic: -descent   hanging: 0.8 * ascent to the nearest 1/64
#   auto, alphabetic, text-top, text-bottom: 0
# with ascent / descent rounded to whole pixels, as for the box itself. The fake measurer gives, at 16px:
# ascent 12.8 (-> 13), descent 3.2 (-> 3), xHeight 8.
_SHIFTS_16PX = {
    "auto": 0, "alphabetic": 0, "text-top": 0, "text-bottom": 0,
    "middle": 4, "central": 5, "mathematical": 6.5, "text-before-edge": 13,
    "text-after-edge": -3, "ideographic": -3, "hanging": 10.40625,
}


def _text_y(setup: str) -> float:
    ctx = _make_ctx()
    return ctx.eval(
        f"""
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(NS, "svg");
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", "5"); t.setAttribute("y", "100"); t.textContent = "Section";
        svg.appendChild(t);
        document.body.appendChild(svg);  // stylesheet rules are looked up through the document
        {setup}
        t.getBBox().y;
        """
    )


@pytest.mark.parametrize("baseline, shift", sorted(_SHIFTS_16PX.items()))
def test_dominant_baseline_in_the_style_attribute_shifts_the_box(baseline, shift):
    plain = _text_y("")
    assert _text_y(f't.setAttribute("style", "font-size: 16px; dominant-baseline: {baseline};");') - \
        _text_y('t.setAttribute("style", "font-size: 16px;");') == shift
    assert plain == _text_y("")


def test_dominant_baseline_as_a_presentation_attribute():
    base = _text_y('t.setAttribute("style", "font-size: 16px;");')
    assert _text_y('t.setAttribute("style", "font-size: 16px;"); t.setAttribute("dominant-baseline", "middle");') - base == 4


def test_dominant_baseline_is_inherited():
    base = _text_y('t.setAttribute("style", "font-size: 16px;");')
    assert _text_y('t.setAttribute("style", "font-size: 16px;"); svg.setAttribute("style", "dominant-baseline: central");') - base == 5


def test_dominant_baseline_from_a_stylesheet_rule():
    base = _text_y('t.setAttribute("style", "font-size: 16px;");')
    css = (
        'const st = document.createElementNS(NS, "style"); st.textContent = ".lbl { dominant-baseline: middle; }"; '
        'svg.appendChild(st); t.setAttribute("class", "lbl"); t.setAttribute("style", "font-size: 16px;");'
    )
    assert _text_y(css) - base == 4


def test_dominant_baseline_through_the_cssom():
    base = _text_y('t.setAttribute("style", "font-size: 16px;");')
    assert _text_y('t.setAttribute("style", "font-size: 16px;"); t.style.setProperty("dominant-baseline", "hanging");') - base == 10.40625


# -- one reader of an element's inline style ---------------------------------------------------------------
@pytest.mark.parametrize("raw, prop, expected", [
    ("a: 1; width: 40px; b: 2", "width", "40px"),
    ("width: 40px !important", "width", "40px !important"),
    ("  white-space : break-spaces ;", "white-space", "break-spaces"),
    ("a: 1", "width", None),
])
def test_inline_style_prop_reads_the_attribute(raw, prop, expected):
    ctx = _make_ctx()
    assert ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "g");
        el.setAttribute("style", {raw!r});
        __inlineStyleProp(el, {prop!r});
        """
    ) == expected


def test_inline_style_prop_sees_a_cssom_write_and_a_removal():
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const el = document.createElementNS("http://www.w3.org/2000/svg", "g");
        el.setAttribute("style", "width: 40px; height: 9px");
        el.style.setProperty("width", "50px");
        el.style.removeProperty("height");
        JSON.stringify([__inlineStyleProp(el, "width"), __inlineStyleProp(el, "height")]);
        """
    )
    assert got == '["50px",null]'


# ---------------------------------------------------------------------------
# One reader for an element's inline style: __resolveFont and the element
# size getters must go through __inlineStyleProp, not re-parse cssText.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, prop, expected", [
    ("font-size : 40px", "size", 40),                  # space before the colon
    ("font-size:40px", "size", 40),
    ("x-font-size: 99px", "size", 16),                 # a different property that ends in the same name
    ("font-size: 20px; font-size: 30px", "size", 30),  # last declaration wins
    ('font-family : "Foo"', "family", '"Foo"'),
    ("x-font-family: Bar", "family", "sans-serif"),
    ("font-weight : bold", "weight", "bold"),
    ("x-font-weight: bold", "weight", "normal"),
])
def test_resolve_font_reads_inline_style_like_a_browser(raw, prop, expected):
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
        el.setAttribute("style", {raw!r});
        __resolveFont(el).{prop};
        """
    )
    assert got == expected


def test_resolve_font_sees_a_cssom_write_and_a_removal():
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
        el.setAttribute("style", "font-size: 20px; font-weight: bold");
        el.style.setProperty("font-size", "30px");
        el.style.removeProperty("font-weight");
        const f = __resolveFont(el);
        JSON.stringify([f.size, f.weight]);
        """
    )
    assert got == '[30,"normal"]'


@pytest.mark.parametrize("raw, expected", [
    ("width: 20px", 20),
    ("width:20.5px", 20.5),
    ("max-width: 5px; width: 20px", 20),   # max-width is not width
    ("min-width: 5px; width: 20px", 20),
    ("max-width: 5px", 1000),              # no width declared: the fallback, not max-width
    ("width: 50%", 1000),                  # not a px length: the fallback
])
def test_offset_width_reads_the_declared_width_only(raw, expected):
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const el = document.createElement("div");
        el.setAttribute("style", {raw!r});
        el.offsetWidth;
        """
    )
    assert got == expected


def test_offset_height_reads_the_declared_height_only():
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const el = document.createElement("div");
        el.setAttribute("style", "max-height: 5px; height: 7px");
        el.offsetHeight;
        """
    )
    assert got == 7


# ---------------------------------------------------------------------------
# HTML (foreignObject) label boxes: the font size handed to the measurer and
# the declared width / max-width clamp.
# ---------------------------------------------------------------------------

def _html_label(setup: str, natural_width: float = 100.0):
    """Build <div id=host><span id=lbl>text</span></div> in the document, run *setup*,
    and return (font size the measurer was asked for, host.getBoundingClientRect().width)."""
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        globalThis.__asked = [];
        globalThis.__measureForeignObject = (html, size, family, weight, style) => {{
          __asked.push(size);
          return {{ width: {natural_width}, height: 20 }};
        }};
        const host = document.createElement("div");
        const lbl = document.createElement("span");
        lbl.textContent = "text";
        host.appendChild(lbl);
        document.body.appendChild(host);
        {setup}
        const r = lbl.getBoundingClientRect();
        JSON.stringify([__asked[0], r.width]);
        """
    )
    return json.loads(got)


_STYLE_RULE = (
    'const st = document.createElementNS("http://www.w3.org/2000/svg", "style"); '
    'st.textContent = "{css}"; document.body.appendChild(st);'
)


@pytest.mark.parametrize("setup, size", [
    ("", 16),
    ('lbl.setAttribute("style", "font-size: 20px");', 20),
    ('host.setAttribute("style", "font-size: 18px");', 18),                       # inherited from the nearest ancestor
    ('host.setAttribute("style", "font-size: 18px"); lbl.setAttribute("style", "font-size: 22px");', 22),
    ('lbl.setAttribute("style", "font-size: 2em");', 16),                         # not a px length: ignored
    ('lbl.setAttribute("style", "font-size: 20");', 16),                          # unitless: invalid CSS, ignored
    ('lbl.setAttribute("style", "font-size: x20px");', 16),                       # not a number
    ('lbl.setAttribute("style", "font-size: 20px 30px");', 16),                   # not a single length
    (_STYLE_RULE.format(css=".big{font-size: 14px }") + 'lbl.setAttribute("class", "big");', 14),
    (_STYLE_RULE.format(css=".big{font-size: 14px}") + 'lbl.setAttribute("class", "big"); lbl.setAttribute("style", "font-size: 30px");', 30),  # inline beats the sheet
    (_STYLE_RULE.format(css=".big{font-size: 2em}") + 'lbl.setAttribute("class", "big");', 16),
])
def test_html_label_font_size_handed_to_the_measurer(setup, size):
    assert _html_label(setup)[0] == size


@pytest.mark.parametrize("setup, width", [
    ("", 100),
    ('host.setAttribute("style", "width: 200px");', 100),                         # the span has no width of its own
    ('lbl.setAttribute("style", "width: 200px");', 200),                          # an explicit width IS the box width
    ('lbl.setAttribute("style", "max-width: 60px");', 60),                        # a natural width is clamped to max-width
    ('lbl.setAttribute("style", "max-width: 500px");', 100),                      # ... but never widened by it
    ('lbl.setAttribute("style", "width: 40px; max-width: 30px");', 30),
    ('lbl.setAttribute("style", "width: 50%");', 100),                            # not a px length: ignored
])
def test_html_label_declared_width_and_max_width(setup, width):
    assert _html_label(setup)[1] == width


# ---------------------------------------------------------------------------
# <text> layout the way SVG does it: an absolute x or y starts a new text chunk, dx/dy shift the position,
# each chunk is anchored on its own advance. (Fake measurer at the default 16px: 8px per character,
# ascent 13, descent 3, x-height 8.)
# ---------------------------------------------------------------------------

def _text_box(markup: str, text_attrs: str = "", css: str = "", svg_attrs: str = ""):
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(NS, "svg");
        document.body.appendChild(svg);
        svg.innerHTML = {('<style>' + css + '</style><text ' + text_attrs + '>' + markup + '</text>')!r};
        {('svg.setAttribute("style", ' + repr(svg_attrs) + ');') if svg_attrs else ''}
        const b = svg.querySelector("text").getBBox();
        JSON.stringify([b.x, b.y, b.width, b.height]);
        """
    )
    return json.loads(got)


_TWO_LINES = '<tspan x="0" dy="0">Blurry</tspan><tspan x="0" dy="16.8">Photo</tspan>'


@pytest.mark.parametrize("anchor, x, width", [
    ("start", 0, 48),
    ("middle", -24, 48),     # each line is centred on its own advance, not the two together
    ("end", -48, 48),
])
def test_tspans_with_an_absolute_x_are_separate_lines(anchor, x, width):
    box = _text_box(_TWO_LINES, f'x="0" y="-8.4" style="text-anchor: {anchor}"')
    assert box == pytest.approx([x, -21.4, width, 32.8], abs=1e-4)


def test_a_shorter_line_does_not_widen_the_box():
    box = _text_box('<tspan x="0" dy="0">Blurry</tspan><tspan x="0" dy="16.8">Hi</tspan>',
                    'x="0" y="-8.4" style="text-anchor: middle"')
    assert box == pytest.approx([-24, -21.4, 48, 32.8], abs=1e-4)


def test_dominant_baseline_moves_every_line():
    plain = _text_box(_TWO_LINES, 'x="0" y="-8.4"')
    middle = _text_box(_TWO_LINES, 'x="0" y="-8.4" style="dominant-baseline: middle"')
    assert middle[1] - plain[1] == pytest.approx(4)   # x-height / 2
    assert middle[3] == plain[3]


def test_tspans_without_a_position_continue_the_line():
    assert _text_box("<tspan>ab</tspan><tspan>cd</tspan>", 'x="5" y="20"') == pytest.approx([5, 7, 32, 16], abs=1e-4)


def test_dx_moves_the_rest_of_the_line_and_widens_the_box():
    assert _text_box('<tspan>ab</tspan><tspan dx="10">cd</tspan>', 'x="0" y="20"') == pytest.approx([0, 7, 42, 16], abs=1e-4)


def test_an_absolute_y_alone_starts_a_chunk_where_the_last_one_ended():
    # "cd" lands at x=16, y=60: the box is the union of both runs.
    assert _text_box('<tspan>ab</tspan><tspan y="60">cd</tspan>', 'x="0" y="20"') == pytest.approx([0, 7, 32, 56], abs=1e-4)


@pytest.mark.parametrize("markup, chars", [
    ("<tspan>a</tspan><tspan> b</tspan>", 3),          # the space between the two runs is kept
    ("<tspan>a </tspan><tspan> b</tspan>", 3),         # ... but two in a row collapse to one
    ("\n  <tspan>a</tspan>\n", 1),                     # leading and trailing space are dropped
    ("<tspan>a</tspan>\n  <tspan>b</tspan>", 3),       # a newline between runs is one space
])
def test_white_space_collapses_across_runs(markup, chars):
    assert _text_box(markup, 'x="0" y="20"')[2] == pytest.approx(chars * 8, abs=1e-4)


def test_title_is_not_part_of_the_text():
    assert _text_box("<title>xxxx</title>ab", 'x="0" y="20"')[2] == pytest.approx(16, abs=1e-4)


# A property set on the <text> reaches its tspans: walking up from a node, the first one that declares it wins, and a
# node's own declaration is its inline style, then a stylesheet rule, then a presentation attribute.
_AB = '<tspan x="0">ab</tspan>'


def test_a_stylesheet_text_anchor_on_the_text_reaches_its_tspans():
    box = _text_box(_AB, 'class="t" text-anchor="start" x="0" y="20"', css=".t{text-anchor: middle}")
    assert box[0] == pytest.approx(-8)


def test_a_stylesheet_dominant_baseline_on_the_text_reaches_its_tspans():
    plain = _text_box(_AB, 'x="0" y="20"')
    shifted = _text_box(_AB, 'class="t" x="0" y="20"', css=".t{dominant-baseline: middle}")
    assert shifted[1] - plain[1] == pytest.approx(4)


def test_the_nearest_declaration_wins():
    # the tspan's own presentation attribute outranks what it would inherit from the text's inline style
    box = _text_box('<tspan x="0" text-anchor="end">ab</tspan>', 'x="0" y="20" style="text-anchor: middle"')
    assert box[0] == pytest.approx(-16)


def test_an_elements_own_stylesheet_rule_beats_an_ancestors_inline_style():
    box = _text_box(_AB, 'class="t" x="0" y="20"', css=".t{text-anchor: middle}", svg_attrs="text-anchor: end")
    assert box[0] == pytest.approx(-8)


def test_an_inline_style_beats_a_stylesheet_rule_which_beats_an_attribute():
    css = ".t{text-anchor: middle}"
    assert _text_box(_AB, 'class="t" text-anchor="end" x="0" y="20"', css=css)[0] == pytest.approx(-8)
    assert _text_box(_AB, 'class="t" text-anchor="end" x="0" y="20" style="text-anchor: start"', css=css)[0] == pytest.approx(0)


@pytest.mark.parametrize("text_attrs", ['xml:space="preserve"', 'style="white-space: pre"'])
def test_white_space_is_kept_when_the_text_asks_for_it(text_attrs):
    assert _text_box("<tspan>a</tspan>  <tspan> b</tspan>", f'x="0" y="20" {text_attrs}')[2] == pytest.approx(5 * 8)


def test_a_run_that_collapses_to_nothing_still_swallows_the_next_space():
    # "a " + " " + " b": the middle run is all space and vanishes, and the space that opens " b" must go too
    assert _text_box("<tspan>a </tspan><tspan> </tspan><tspan> b</tspan>", 'x="0" y="20"')[2] == pytest.approx(3 * 8)


def test_an_absolute_y_alone_is_a_new_chunk_with_its_own_anchor():
    # "ab" is centred on x=0 (-8..8); "cd" starts a chunk at x=16 and is centred there on its own advance (8..24)
    box = _text_box('<tspan>ab</tspan><tspan y="60">cd</tspan>', 'x="0" y="20" style="text-anchor: middle"')
    assert box[0] == pytest.approx(-8) and box[2] == pytest.approx(32)


def test_dx_is_added_in_float32():
    # x = f32(37.91749794) + f32(0.42109141), kept in float32, then the chunk's own advance (16) is centred
    box = _text_box('<tspan dx="0.42109141">ab</tspan>', 'x="37.91749794" y="20" style="text-anchor: middle"')
    assert box[0] == 30.338592529296875


def test_a_chunk_is_anchored_by_its_first_character():
    box = _text_box('<tspan text-anchor="start">ab</tspan><tspan text-anchor="end">cd</tspan>', 'x="0" y="20"')
    assert box[0] == 0 and box[2] == pytest.approx(32)


def test_em_in_a_tspan_is_its_own_font_size():
    # dy="1em" on a 20px tspan inside 10px text moves the baseline 20, not 10; ascent 16, descent 4 at 20px
    box = _text_box('<tspan style="font-size: 20px" dy="1em">a</tspan>', 'x="0" y="0" style="font-size: 10px"')
    assert box[1] == pytest.approx(20 - 16) and box[3] == pytest.approx(20)


@pytest.mark.parametrize("markup", ["", " ", "<tspan></tspan>", "\n  "])
def test_text_without_characters_has_an_empty_box(markup):
    """Chrome (tests/data/chrome_text_bbox.json): an empty <text> -- or one holding only space -- is 0,0,0,0,
    wherever it is positioned."""
    assert _text_box(markup, 'x="5" y="20"') == [0, 0, 0, 0]


# ---------------------------------------------------------------------------
# Namespaced attributes. d3's attr("xlink:href", v) calls setAttributeNS(XLINK, "href", v) -- the local name -- and
# a serializer gives an attribute that has a namespace and no prefix the namespace's well-known prefix.
# ---------------------------------------------------------------------------

_XLINK = "http://www.w3.org/1999/xlink"
_XML_NS = "http://www.w3.org/XML/1998/namespace"


def _serialized(js: str):
    ctx = _make_ctx()
    return ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "image");
        {js}
        JSON.stringify([new XMLSerializer().serializeToString(el), el.outerHTML]);
        """
    )


@pytest.mark.parametrize("call, attr", [
    (f'el.setAttributeNS("{_XLINK}", "href", "x");', ' xlink:href="x"'),
    (f'el.setAttributeNS("{_XLINK}", "xlink:href", "x");', ' xlink:href="x"'),       # already prefixed: not doubled
    (f'el.setAttributeNS("{_XML_NS}", "space", "preserve");', ' xml:space="preserve"'),
    ('el.setAttributeNS(null, "href", "x");', ' href="x"'),                           # no namespace, no prefix
    ('el.setAttribute("href", "x");', ' href="x"'),
    (f'el.setAttributeNS("{_XLINK}", "href", "x"); el.setAttribute("href", "y");', ' xlink:href="y"'),   # a value change keeps the namespace
    (f'el.setAttributeNS("{_XLINK}", "href", "x"); el.removeAttribute("href"); el.setAttribute("href", "y");', ' href="y"'),
])
def test_namespaced_attributes_are_serialized_with_their_prefix(call, attr):
    xml, html = json.loads(_serialized(call))
    assert attr in xml
    assert attr in html


def test_xlink_attribute_declares_its_prefix_once():
    xml, _ = json.loads(_serialized(f'el.setAttributeNS("{_XLINK}", "href", "x");'))
    assert xml == f'<image xmlns="http://www.w3.org/2000/svg" xmlns:xlink="{_XLINK}" xlink:href="x"/>'


def test_a_clone_keeps_the_namespace_of_its_attributes():
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "image");
        el.setAttributeNS("{_XLINK}", "href", "x");
        const clone = el.cloneNode(true);
        el.removeAttribute("href");   // the clone must not share the original's bookkeeping
        new XMLSerializer().serializeToString(clone);
        """
    )
    assert ' xlink:href="x"' in got


def test_attributes_report_their_namespace():
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const el = document.createElementNS("http://www.w3.org/2000/svg", "image");
        el.setAttributeNS("{_XLINK}", "href", "x");
        el.setAttribute("id", "i");
        JSON.stringify(Array.from(el.attributes).map((a) => [a.name, a.namespaceURI]));
        """
    )
    assert json.loads(got) == [["href", _XLINK], ["id", None]]


def test_the_screen_is_the_page_mmdc_opens():
    """mermaid's C4 diagram wraps its rows at screen.availWidth. mmdc's page has a 800x600 viewport, which
    also sizes the screen; with the 1920 this shim once had, a C4 diagram laid out four to a row where mmdc's
    wraps after the first (tests/samples/24_c4_context.svg)."""
    ctx = _make_ctx()
    assert json.loads(ctx.eval("JSON.stringify([screen.width, screen.height, screen.availWidth, screen.availHeight])")) == [800, 600, 800, 600]


# ---------------------------------------------------------------------------
# One grammar and one unit table behind every length (CSS font sizes, px lengths, SVG attributes).
# The SVG side is pinned against Chrome in tests/test_shape_bbox_chrome.py.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, px", [
    ("12px", 12), ("1in", 96), ("1pc", 16), ("72pt", 96), ("2.54cm", 96), ("25.4mm", 96), ("2rem", 32),
    ("2em", 28), ("2ex", 2 * 14 * 1120 / 2048), ("50%", 7), ("+3px", 3), (".5px", 0.5), ("1e1px", 10), ("12PX", 12), ("  12px ", 12), ("12", 12),
    ("5.", None), ("10 px", None), ("10abc", None), ("1.2.3px", None), ("", None), ("px", None), ("calc(1px)", None),
])
def test_css_length_to_px(value, px):
    ctx = _make_ctx()
    got = ctx.eval(f"__lenToPx({value!r}, 14)")
    assert got == (pytest.approx(px, abs=1e-9) if px is not None else None)


@pytest.mark.parametrize("value, expected", [
    ("12px", 12), ("12.5px", 12.5), ("0px", 0), ("PX", None), ("12PX", 12), (" 12px ", 12),
    ("-5px", None), ("12", None), ("12em", None), ("12%", None), ("12 px", None), ("", None), (None, None),
])
def test_px_value_is_a_non_negative_px_length_only(value, expected):
    ctx = _make_ctx()
    assert ctx.eval(f"__pxValue({json.dumps(value)})") == expected


@pytest.mark.parametrize("text, numbers", [
    ("0,0 10,5", [0, 0, 10, 5]),
    ("  1 , 2   3 ", [1, 2, 3]),
    ("10-5", [10, -5]),                 # a sign starts the next number
    ("1.5.5", [1.5, 0.5]),              # so does a second dot
    ("1e1,2E-1", [10, 0.2]),
    ("+1 -2", [1, -2]),
    ("1,2 a,b 3,4", [1, 2]),            # stops at the first thing that is not a number
    ("1,2 3px,4", [1, 2, 3]),
    ("1e", [1]),
    ("a", []), ("", []), (",", []),
])
def test_number_list_is_read_up_to_the_first_error(text, numbers):
    ctx = _make_ctx()
    got = json.loads(ctx.eval(f"JSON.stringify(__parseNumberList({text!r}))"))
    assert got == pytest.approx(numbers, abs=1e-6)


def test_number_list_numbers_are_float32():
    ctx = _make_ctx()
    assert ctx.eval('__parseNumberList("0.1,0.30000000000000004").every((v, i) => v === Math.fround([0.1, 0.30000000000000004][i]))')


@pytest.mark.parametrize("attrs, name, expected", [
    ('x="-5"', "x", -5),                    # a coordinate may be negative
    ('width="-5"', "width", 0),             # a size may not
    ('r="-5"', "r", 0), ('rx="-5"', "rx", 0), ('ry="-5"', "ry", 0), ('height="-5"', "height", 0),
    ('cx="-5"', "cx", -5), ('y1="-5"', "y1", -5),
    ('width="abc"', "width", 0), ("", "width", 0),
])
def test_a_shapes_length_is_zero_when_missing_invalid_or_a_negative_size(attrs, name, expected):
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const holder = document.createElement("div");
        holder.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg"><rect {attrs}/></svg>';
        __shapeLength(holder.querySelector("rect"), "{name}");
        """
    )
    assert got == expected


@pytest.mark.parametrize("svg_attrs, expected", [
    ('width="400" height="300"', [40, 30]),
    ('width="400" height="300" viewBox="0 0 200 100"', [20, 10]),
    ('width="400" height="300" viewBox="0,0,200,100"', [20, 10]),
    ('width="400" height="300" viewBox="0 0 200"', [40, 30]),           # not a viewBox: width and height
    ('width="50%" height="300"', [0, 30]),                              # a percentage of nothing: the outermost svg has no viewport
    ('width="40mm"', [round(40 * 96 / 25.4 / 10, 4), 0]),
    ("", [0, 0]),
])
def test_percent_lengths_use_the_viewbox_else_width_and_height(svg_attrs, expected):
    ctx = _make_ctx()
    got = json.loads(ctx.eval(
        f"""
        const holder = document.createElement("div");
        holder.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" {svg_attrs}><rect x="10%" y="10%"/></svg>';
        const r = holder.querySelector("rect");
        JSON.stringify([__svgLength(r, "x"), __svgLength(r, "y")]);
        """
    ))
    assert got == pytest.approx(expected, abs=1e-3)


def test_percent_lengths_use_the_nearest_svg():
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const holder = document.createElement("div");
        holder.innerHTML = '<svg viewBox="0 0 1000 1000"><svg viewBox="0 0 200 100"><rect x="10%"/></svg></svg>';
        __svgLength(holder.querySelector("rect"), "x");
        """
    )
    assert got == 20


def test_a_detached_element_has_no_viewport():
    ctx = _make_ctx()
    assert ctx.eval('const r = document.createElementNS("http://www.w3.org/2000/svg", "rect"); r.setAttribute("x", "10%"); __svgLength(r, "x")') == 0


# ---------------------------------------------------------------------------
# Timers are a browser's macrotask queue, on virtual time: nothing runs until the engine calls __runNextTimer(),
# which runs the one that is due first (ties: in the order they were scheduled). Promise jobs run between them.
# ---------------------------------------------------------------------------

def _timers(js: str):
    """Run *js* (which pushes to `out`), then every timer to exhaustion; return `out`."""
    ctx = _make_ctx()
    got = ctx.eval(
        f"""
        const out = [];
        {js}
        let guard = 0;
        while (__runNextTimer() && ++guard < 100) {{}}
        JSON.stringify(out);
        """
    )
    return json.loads(got)


def test_a_timer_does_not_run_until_the_engine_runs_it():
    ctx = _make_ctx()
    assert ctx.eval('const hits = []; setTimeout(() => hits.push(1), 0); hits.length') == 0
    assert ctx.eval("__runNextTimer()") is True
    assert ctx.eval("hits.length") == 1
    assert ctx.eval("__runNextTimer()") is False


def test_timers_run_earliest_due_first_and_ties_in_scheduling_order():
    assert _timers('setTimeout(() => out.push("b"), 10); setTimeout(() => out.push("a"), 0); setTimeout(() => out.push("c"), 10);') == ["a", "b", "c"]


def test_a_timer_scheduled_by_a_timer_goes_behind_those_already_due():
    assert _timers(
        'setTimeout(() => { out.push(1); setTimeout(() => out.push(3), 0); }, 0); setTimeout(() => out.push(2), 0);'
    ) == [1, 2, 3]


def test_time_is_virtual_so_a_long_delay_costs_nothing_but_still_orders():
    assert _timers('setTimeout(() => out.push("late"), 100000); setTimeout(() => out.push("soon"), 5);') == ["soon", "late"]


def test_a_delay_counts_from_when_the_timer_was_scheduled():
    # at t=10 the first timer schedules one 5 later (due 15); the second was due at 12, so it goes first
    assert _timers(
        'setTimeout(() => { out.push("a"); setTimeout(() => out.push("c"), 5); }, 10); setTimeout(() => out.push("b"), 12);'
    ) == ["a", "b", "c"]


def test_negative_missing_and_nonnumeric_delays_are_zero():
    assert _timers('setTimeout(() => out.push("b"), "x"); setTimeout(() => out.push("a"), -5); setTimeout(() => out.push("c"));') == ["b", "a", "c"]


def test_extra_arguments_reach_the_callback():
    assert _timers("setTimeout((a, b) => out.push(a + b), 0, 1, 2);") == [3]


def test_clear_timeout_cancels_and_an_unknown_id_is_ignored():
    assert _timers('const id = setTimeout(() => out.push("x"), 0); setTimeout(() => out.push("y"), 0); clearTimeout(id); clearTimeout(12345); clearTimeout(undefined);') == ["y"]


def test_set_timeout_returns_distinct_ids():
    assert _timers("const a = setTimeout(() => {}, 0), b = setTimeout(() => {}, 0); out.push(a !== b, a > 0, b > 0);") == [True, True, True]


def test_an_interval_repeats_until_it_is_cleared():
    assert _timers('let n = 0; const id = setInterval(() => { out.push(++n); if (n === 3) clearInterval(id); }, 10);') == [1, 2, 3]


def test_an_interval_runs_in_step_with_other_timers():
    assert _timers(
        'let n = 0; const id = setInterval(() => { out.push("i"); if (++n === 3) clearInterval(id); }, 10); setTimeout(() => out.push("t"), 15);'
    ) == ["i", "t", "i", "i"]


def test_a_cleared_interval_does_not_run_again():
    assert _timers('const id = setInterval(() => out.push("x"), 10); clearInterval(id);') == []


def test_animation_frames_run_on_a_16ms_grid_and_get_a_timestamp():
    assert _timers('requestAnimationFrame((t) => out.push(t));') == [16]


def test_a_frame_requested_in_a_frame_is_the_next_frame():
    assert _timers(
        'requestAnimationFrame((t) => { out.push(t); requestAnimationFrame((u) => out.push(u)); });'
    ) == [16, 32]


def test_a_timer_due_before_the_next_frame_runs_before_it():
    assert _timers('requestAnimationFrame(() => out.push("frame")); setTimeout(() => out.push("t"), 5);') == ["t", "frame"]


def test_cancel_animation_frame():
    assert _timers('const id = requestAnimationFrame(() => out.push("x")); requestAnimationFrame(() => out.push("y")); cancelAnimationFrame(id);') == ["y"]


def test_a_throwing_callback_does_not_stop_the_queue():
    assert _timers('setTimeout(() => { throw new Error("boom"); }, 0); setTimeout(() => out.push("after"), 0);') == ["after"]


def test_a_frame_loop_that_never_stops_is_bounded_by_the_engine_not_the_page():
    # what cytoscape does: every frame asks for the next one. Each __runNextTimer() runs exactly one frame.
    ctx = _make_ctx()
    ctx.eval("let frames = 0; const loop = () => { frames++; requestAnimationFrame(loop); }; requestAnimationFrame(loop);")
    for _ in range(50):
        assert ctx.eval("__runNextTimer()") is True
    assert ctx.eval("frames") == 50
