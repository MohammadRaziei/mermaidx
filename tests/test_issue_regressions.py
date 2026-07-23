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


def test_issue_23_block_chart_with_nested_block_and_style():
    """https://github.com/MohammadRaziei/mermaidx/issues/23

    Block diagrams with a nested `block:ID ... end` group used to crash
    with "TypeError: circular reference". Root cause: mermaid's block
    layout stashes a live d3 selection (wrapping a DOM node) inside a
    plain `size` object, then JSON.stringify's that object in a debug-log
    line. The shim's DOM nodes store parentNode/childNodes as own
    enumerable instance properties (real browsers use non-enumerable
    prototype getters instead), so without a Node.toJSON() short-circuit,
    that JSON.stringify call walks the whole parent<->child graph and
    hits a genuine cycle.
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
    # The styled block's fill color should make it into the output.
    assert "#f9F" in svg or "#ff99ff" in svg.lower()
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
