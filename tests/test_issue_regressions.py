"""End-to-end regression tests for specific GitHub issues, rendering the
exact (or lightly trimmed) diagram source reported in each issue through
the full mermaidx.render().svg() path -- not just the isolated dom_shim
unit, so a fix can't silently break somewhere else in the pipeline.
"""

from __future__ import annotations

import re

import pytest

quickjs = pytest.importorskip("quickjs")

import mermaidx


def test_issue_25_click_links_with_https_url():
    """https://github.com/MohammadRaziei/mermaidx/issues/25

    A `click node "https://..."` handler used to crash with
    "ReferenceError: URL is not defined", since QuickJS has no built-in
    URL and mermaid's click-href sanitizer needs one for http(s) links.
    Non-http(s) schemes (mailto, anchors, custom protocols, javascript:)
    never reach `new URL(...)` and are included here to guard against a
    regression narrowly scoped to only the https branch.
    """
    code = """graph TB
    TITLE["Link Click Events"]
    A["same tab"]
    B["new tab"]
    C[anchor test]
    D[mailto test]
    E[other protocol test]
    F[script test]
    TITLE --> A & B & C & D & E & F
    click A "https://mermaid-js.github.io/mermaid/#/" "same tab"
    click B "https://mermaid-js.github.io/mermaid/#/" "new tab" _blank
    click C "#link-clicked"
    click D "mailto:user@user.user" "mailto test"
    click E "notes://do-your-thing/id" "other protocol test"
    click F "javascript:alert('test')" "script test"
    """
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    assert "TITLE" in svg
    # The two http(s) links must survive sanitization and appear as <a> hrefs.
    assert 'href="https://mermaid-js.github.io/mermaid/#/"' in svg


def test_issue_24_sankey_chart():
    """https://github.com/MohammadRaziei/mermaidx/issues/24

    Sankey diagrams used to crash with "TypeError: not a function": d3
    selection's .order() (used to reorder sankey's <g> layers) calls
    node.compareDocumentPosition(), which the fake DOM never implemented.
    """
    code = """sankey

    iPhone,Products,205
    Mac,Products,40
    iPad,Products,29
    Wearables,Products,41
    Products,Revenue,315
    Services,Revenue,78
    Revenue,Cost of Revenue,223
    Revenue,Gross Profit,170
    Gross Profit,Op Expenses,51
    Gross Profit,Op Profit,119
    Op Profit,Tax,19
    Op Profit,Net Profit,100
    """
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    # A handful of the node labels should make it into the rendered output.
    assert "iPhone" in svg
    assert "Revenue" in svg


def test_issue_27_sequence_box_groups():
    """https://github.com/MohammadRaziei/mermaidx/issues/27

    A `box <color> <participants>` group in a sequenceDiagram used to crash
    with "ReferenceError: Option is not defined". mermaid's box-color
    parser first tries `window.CSS.supports("color", name)` to check
    whether the leading word is a real CSS color, only falling back to a
    `new Option().style.color = ...` browser trick when `CSS` is missing --
    QuickJS has neither, so it always hit the unimplementable fallback.

    Fixing just that crash wasn't the whole story, though: the box then
    rendered as an opaque rect covering the *entire* diagram, hiding the
    actors and messages behind it, because mermaid draws the box first and
    calls d3 selection's `.lower()` to push it behind everything appended
    after it -- and `.lower()` silently no-ops without a `previousSibling`
    getter on Node, which the shim never had. So this checks not just that
    rendering succeeds, but that the box rect actually ends up before (i.e.
    behind, in SVG paint order) the actor rects in the document.
    """
    code = """sequenceDiagram
    box Purple Alice & John
    participant Alice
    participant John
    end
    Alice->>John: Hello John, how are you?
    John-->>Alice: Great!
    """
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    assert "Alice" in svg and "John" in svg

    box_match = re.search(r'<rect[^>]*fill="Purple"[^>]*class="rect"', svg)
    actor_match = re.search(r'<rect[^>]*class="actor', svg)
    assert box_match is not None, "expected a purple box <rect> in the output"
    assert actor_match is not None, "expected actor <rect>s in the output"
    assert box_match.start() < actor_match.start(), (
        "the box rect must come before (be drawn behind) the actor rects, "
        "not painted on top of them"
    )


def test_issue_27_sequence_box_without_a_valid_color():
    """When the leading word isn't a real CSS color, mermaid treats the
    whole string as the participant list instead -- must not crash either
    way now that CSS.supports is implemented."""
    code = """sequenceDiagram
    box Alice & John
    participant Alice
    participant John
    end
    Alice->>John: hi
    """
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")


def test_issue_23_block_diagram_with_composite_block():
    """https://github.com/MohammadRaziei/mermaidx/issues/23

    A block diagram containing a composite `block:ID ... end` used to crash
    with "TypeError: circular reference": mermaid's block-layout code logs a
    debug message that JSON.stringify()s internal node/size state (purely
    for the log line, never anything that reaches the SVG), and that state
    can legitimately contain a cycle. QuickJS-ng's native JSON.stringify
    throws on cycles instead of silently truncating them like some engines'
    console formatters do, so the fix makes JSON.stringify itself
    cycle-safe (substituting "[Circular]") rather than throwing.
    """
    code = """block
    columns 1
      db(("DB"))
      blockArrowId6<["&nbsp;&nbsp;&nbsp;"]>(down)
      block:ID
        A
        B["A wide one in the middle"]
        C
      end
      space
      D
      ID --> D
      C --> D
      style B fill:#f9F,stroke:#333,stroke-width:4px
    """
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    assert "DB" in svg


def test_issue_26_yaml_frontmatter():
    """https://github.com/MohammadRaziei/mermaidx/issues/26

    A diagram beginning with a YAML front-matter block (`--- ... ---`)
    used to crash with mermaid's own "Diagrams beginning with --- are not
    valid" error. Covers a flowchart as reported, plus the `config:`
    front-matter key actually taking effect.
    """
    code = """---
title: Subgraph nodeSpacing and rankSpacing example
config:
  flowchart:
    nodeSpacing: 1
    rankSpacing: 1
---

flowchart LR

X --> Y

subgraph X
  direction LR
  A
  C
end

subgraph Y
  direction LR
  B
  D
end
"""
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    assert "A" in svg and "B" in svg


def test_issue_28_treemap_value_label_position():
    """https://github.com/MohammadRaziei/mermaidx/issues/28

    Treemap value labels (the small number under a leaf's name) rendered at
    `y="NaN"` -- landing at the same spot as the leaf label instead of just
    below it -- because mermaid sets the label's initial font-size only via
    d3's `.attr("style", "...")` (which the shim stored on the element's
    raw attribute string) and later reads it back via `.style("font-size")`
    (which only checked the live style-property store) to size and place
    the value label. The fix makes the live style store fall back to
    parsing the style attribute string, matching how a real browser's
    el.style reflects the style="..." attribute.
    """
    code = """treemap-beta
    "Section 1"
        "Leaf 1.1": 12
        "Section 1.2"
        "Leaf 1.2.1": 12
    "Section 2"
        "Leaf 2.1": 20
        "Leaf 2.2": 25
"""
    svg = mermaidx.render(code).svg()
    assert svg.startswith("<svg")
    value_ys = re.findall(r'<text class="treemapValue"[^>]*\by="([^"]*)"', svg)
    assert value_ys, "expected at least one treemapValue text element"
    for y in value_ys:
        assert y != "NaN", "treemapValue label must not land at y=NaN"