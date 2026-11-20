"""ZenUML (issue #20). It is not part of mermaid's core, and its mermaid plugin needs a browser to measure HTML, so
mermaidx runs the SVG renderer that is inside the command line tool of @zenuml/core (assets/zenuml.js, built by
tools/build_zenuml.sh) for a diagram that starts with `zenuml`."""
import re

import pytest

import mermaidx
from mermaidx.engines import _common

SIMPLE = """zenuml
    title Annotators
    @Actor Alice
    @Database Bob
    Alice->Bob: Hi Bob
    Bob->Alice: Hi Alice
"""

RICH = """zenuml
    title Order Service
    @Actor Client
    @Database DB
    OrderService
    Client->OrderService.create(order) {
      if (order.valid) {
        DB.save(order)
        return ok
      } else {
        return error
      }
      while (retry) {
        OrderService->OrderService.again()
      }
    }
"""


def _size(svg: str):
    w, h = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups()
    return float(w), float(h)


@pytest.mark.parametrize(
    "code, expected",
    [
        (SIMPLE, True),
        ("   \n  zenuml\n  A->B: hi", True),
        ("---\ntitle: x\n---\nzenuml\n  A->B: hi", True),
        ('%%{init: {"theme": "dark"}}%%\nzenuml\n  A->B: hi', True),
        ("%% a comment\nzenuml\n  A->B: hi", True),
        ("flowchart TD\n  A --> B", False),
        ("sequenceDiagram\n  A->>B: zenuml", False),  # the word somewhere else is not the diagram type
        ("", False),
    ],
)
def test_needs_zenuml(code, expected):
    assert _common.needs_zenuml(code) is expected


def test_the_body_is_what_follows_the_zenuml_line():
    # the plugin of mermaid does the same: without it `zenuml` and `title` would come out as participants
    assert _common.zenuml_body("---\ntitle: x\n---\nzenuml\n  A->B: hi").strip() == "A->B: hi"


def test_zenuml_script_is_only_part_of_the_render_script_of_a_zenuml_diagram():
    plain = _common.render_script("flowchart TD\n  A --> B", None, None, None)
    zen = _common.render_script(SIMPLE, None, None, None)
    assert "__zenuml" not in plain and len(plain) < 20_000
    assert zen.startswith("/* @zenuml/core") and len(zen) > 300_000
    assert "__zenuml" not in _common.render_script(SIMPLE, None, None, None, library="pele")
    assert not any("@zenuml/core" in script for script in _common.context_scripts("mermaid"))


@pytest.mark.parametrize("engine", ["quickjs", "v8"])
def test_zenuml_renders_to_a_plain_svg(engine):
    if engine == "v8":
        pytest.importorskip("py_mini_racer")
    svg = mermaidx.render(SIMPLE, engine=engine).svg()
    assert svg.lstrip().startswith("<svg") and "foreignObject" not in svg
    for text in ("Annotators", "Alice", "Bob", "Hi Bob", "Hi Alice"):
        assert text in svg
    # `zenuml` is the diagram type, not a participant
    assert ">zenuml<" not in svg
    width, height = _size(svg)
    assert width > 100 and height > 100


def test_a_zenuml_diagram_with_fragments_has_all_of_its_parts():
    svg = mermaidx.render(RICH).svg()
    for text in ("Order Service", "Client", "DB", "OrderService", "create(order)", "save(order)", "again()", "Alt", "Loop"):
        assert text in svg


def test_frontmatter_and_directives_before_zenuml_are_dropped():
    plain = mermaidx.render(SIMPLE).svg()
    assert mermaidx.render("---\ntitle: ignored by zenuml\n---\n" + SIMPLE).svg() == plain
    assert mermaidx.render('%%{init: {"theme": "dark"}}%%\n' + SIMPLE).svg() == plain


def test_the_text_is_measured_with_real_font_metrics_not_estimated():
    # without a canvas, ZenUML estimates the width of a text per character; in the context of mermaidx it gets the
    # widths of the bundled font from the DOM shim, so a long label makes its participant box wider
    short = mermaidx.render("zenuml\n  A->B: hi").svg()
    long = mermaidx.render("zenuml\n  A->B: hi\n  A->B: a message with quite a long text on one line").svg()
    assert _size(long)[0] > _size(short)[0]


def test_zenuml_png_and_pdf():
    d = mermaidx.render(SIMPLE)
    assert d.png().startswith(b"\x89PNG")
    assert d.pdf().startswith(b"%PDF")


def test_an_empty_zenuml_diagram_is_an_empty_frame_as_in_zenuml():
    svg = mermaidx.render("zenuml").svg()
    assert svg.lstrip().startswith("<svg") and ">zenuml<" not in svg


def test_a_diagram_after_a_zenuml_one_is_a_normal_mermaid_diagram():
    before = mermaidx.render("flowchart TD\n  A --> B").svg()
    mermaidx.render(SIMPLE).svg()
    assert mermaidx.render("flowchart TD\n  A --> B").svg() == before


def test_pele_does_not_know_zenuml():
    with pytest.raises(RuntimeError, match="No diagram type detected"):
        mermaidx.render(SIMPLE, backend="js:pele").svg()


# The QuickJS engine keeps the context of a ZenUML render for the next ZenUML diagram: the first render in a context
# builds the parser tables of the grammar (over a second), a later one does not. That is only allowed if the second
# diagram comes out as it would in a context of its own.
FRAGMENTS = """zenuml
    title Checkout
    @Actor Client
    @Database DB
    Client->Server.checkout(cart) {
      par {
        Server->Stock.reserve(cart)
        Server->Payment.charge(cart)
      }
      try {
        DB.commit()
      } catch {
        Server->Client: failed
      } finally {
        Server.log()
      }
      return receipt
    }
"""


def _render_in(engine, code):
    return engine.render_svg(code, None, None, None)


def test_zenuml_diagrams_in_one_reused_context_come_out_as_in_a_context_of_their_own():
    from mermaidx.engines.quickjs_engine import Engine

    sources = [RICH, SIMPLE, FRAGMENTS, RICH, FRAGMENTS, SIMPLE]  # every order, repeats too
    fresh = []
    for source in sources:
        alone = Engine()
        alone.start()
        try:
            fresh.append(_render_in(alone, source))
        finally:
            alone.close()
    shared = Engine()
    shared.start()
    try:
        in_one_context = [_render_in(shared, source) for source in sources]
        assert shared._zen_renders == len(sources)  # they really did share a context
    finally:
        shared.close()
    assert in_one_context == fresh


def test_a_zenuml_context_has_no_mermaid_js_and_mermaid_diagrams_do_not_use_it():
    from mermaidx.engines.quickjs_engine import Engine

    assert _common.zenuml_context_scripts() == _common.context_scripts()[:2]  # the bytecode cache names rely on this
    engine = Engine()
    engine.start()
    try:
        _render_in(engine, SIMPLE)
        zen = engine._zen_ctx
        assert zen is not None and zen.eval("typeof globalThis.mermaid") == "undefined"
        assert zen.memory()["memory_used_size"] < 15_000_000  # not the 35 MB of a context with mermaid.js
        flow = _render_in(engine, "graph TD\nA-->B")  # a normal diagram in between ...
        assert "<svg" in flow and engine._zen_ctx is zen and engine._zen_renders == 1
        _render_in(engine, RICH)  # ... and the ZenUML context is still the one that renders the next ZenUML diagram
        assert engine._zen_ctx is zen and engine._zen_renders == 2
    finally:
        engine.close()


def test_a_failed_zenuml_render_does_not_leave_its_context_to_the_next_one(monkeypatch):
    from mermaidx.engines import quickjs_engine

    engine = quickjs_engine.Engine()
    engine.start()
    try:
        _render_in(engine, SIMPLE)
        assert engine._zen_ctx is not None
        real = quickjs_engine.collect_svg

        def failing(evaluate):
            raise _common.MermaidRenderError("stopped halfway")

        monkeypatch.setattr(quickjs_engine, "collect_svg", failing)
        with pytest.raises(_common.MermaidRenderError):
            _render_in(engine, RICH)
        monkeypatch.setattr(quickjs_engine, "collect_svg", real)
        assert engine._zen_ctx is None  # whatever the failed render left behind is thrown away
        assert "<svg" in _render_in(engine, SIMPLE) and engine._zen_renders == 1  # a new context, counted from one
    finally:
        engine.close()


def test_a_zenuml_context_is_replaced_after_the_reuse_limit(monkeypatch):
    from mermaidx.engines import quickjs_engine

    monkeypatch.setattr(quickjs_engine, "CONTEXT_REUSE_LIMIT", 2)
    engine = quickjs_engine.Engine()
    engine.start()
    try:
        counts = []
        for _ in range(5):
            _render_in(engine, SIMPLE)
            counts.append(engine._zen_renders)
        assert counts == [1, 2, 1, 2, 1]
    finally:
        engine.close()


def test_zenuml_on_v8_in_one_reused_context_comes_out_as_in_an_engine_of_its_own():
    pytest.importorskip("py_mini_racer")
    from mermaidx.engines import v8_engine

    flow = "graph TD\n  A --> B"
    sources = [RICH, flow, FRAGMENTS, SIMPLE, flow, RICH]  # mermaid diagrams in between must not be touched
    shared = v8_engine.Engine()
    shared.start()
    try:
        in_one_engine = [_render_in(shared, source) for source in sources]
    finally:
        shared.close()
    for source, svg in zip(sources, in_one_engine):
        alone = v8_engine.Engine()  # a new engine: a new child process, so every context in it is a fresh one
        alone.start()
        try:
            assert _render_in(alone, source) == svg
        finally:
            alone.close()
