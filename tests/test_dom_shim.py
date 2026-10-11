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
            {"width": len(t or "") * s * 0.5, "ascent": s * 0.8, "descent": s * 0.2}
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
    assert ctx.eval('__parseLen("8.855451867927453", 14) === Math.fround(8.855451867927453)')


def test_em_length_is_a_float32_product():
    ctx = _make_ctx()
    assert ctx.eval('__parseLen("1.1em", 14) === Math.fround(Math.fround(1.1) * 14)')


def test_dy_is_added_in_float32():
    ctx = _make_ctx()
    got = ctx.eval(
        """
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("y", "8.855451867927453");
        t.setAttribute("dy", "0.3");
        __resolveTextPos(t, 14).y === Math.fround(Math.fround(8.855451867927453) + Math.fround(0.3));
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
