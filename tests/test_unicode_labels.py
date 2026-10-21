"""Labels holding characters above U+00FF (issue #39).

QuickJS-ng keeps a long concatenation as a rope string, and the quickjs Python binding converts only flat ones,
so any such string reaching Python raised "TypeError: Unknown quickjs tag: -6" (or SystemError inside a
callback). Which strings stay ropes depends on their length and on whether they need 16-bit storage, so the
trigger is any character above U+00FF: a Persian letter, an em dash, a bullet, CJK, an emoji.

A rope can reach Python through any diagram type, any output format, the error path and any callback argument,
so each of those is pinned here. tests/test_issue_regressions.py holds the original reproductions.

https://github.com/MohammadRaziei/mermaidx/issues/39
"""

from __future__ import annotations

import importlib.util

import pytest

quickjs = pytest.importorskip("quickjs")

import mermaidx  # noqa: E402
from mermaidx.engines._common import MermaidRenderError  # noqa: E402
from mermaidx.engines.quickjs_engine import _FLATTEN_JS  # noqa: E402

# Persian for "test". Every letter is above U+00FF, which is all that matters here.
WORD = "آزمون"

# Each template places {word} where the text under test goes, next to the other characters from the report
# (em dash, bullet, >=, circled digit). {word} is substituted with str.replace, so the literal braces that
# mermaid syntax needs (the "o{" of an ER relation) can stay as they are.
TEMPLATES = {
    "flowchart": 'flowchart LR\n    A["{word} — ≥65"] --> B["① next • step"]',
    "sequence": "sequenceDiagram\n    A->>B: {word} — ≥65",
    "journey": "journey\n    title {word} — plan\n    section ① Start\n      Enrol — screen: 5: Me",
    "timeline": "timeline\n    title {word} — history\n    2024 : kickoff ≥65\n    2025 : launch • review",
    "gantt": (
        "gantt\n    title {word}\n    dateFormat YYYY-MM-DD\n"
        "    section ① Phase\n    Task — one :a1, 2024-01-01, 3d"
    ),
    "class": 'classDiagram\n    class Study["{word} — arm"]\n    Study : +age ≥ 65',
    "state": 'stateDiagram-v2\n    state "{word} — arm" as S1\n    [*] --> S1\n    S1 --> [*] : ≥65 • done',
    "er": 'erDiagram\n    STUDY ||--o{ ARM : "{word} — ≥65"',
    "mindmap": "mindmap\n  root(({word}))\n    ① first\n    ≥65 — second",
    "pie": 'pie title {word} — ≥65\n    "① a" : 40\n    "b • c" : 60',
}

HAS_V8 = importlib.util.find_spec("py_mini_racer") is not None


def source(kind: str) -> str:
    return TEMPLATES[kind].replace("{word}", WORD)


def test_every_template_places_the_word():
    """Guards the tests below: each one asserts WORD comes out, so each template has to put it in."""
    assert [kind for kind, template in TEMPLATES.items() if "{word}" not in template] == []


@pytest.mark.parametrize("kind", TEMPLATES)
def test_text_survives_in_every_diagram_type(kind):
    """Not just "it renders": the text has to come out in the svg. Checking only that the output starts with
    <svg would also pass for a render that silently dropped the label."""
    svg = mermaidx.render(source(kind)).svg()
    assert svg.lstrip().startswith("<svg")
    assert WORD in svg


def test_text_reaches_every_output_format():
    """png() and pdf() are built from the svg, so a flat svg has to stay usable for both."""
    d = mermaidx.render(source("flowchart"))
    assert WORD in d.svg()
    assert d.png().startswith(b"\x89PNG\r\n\x1a\n")
    assert d.pdf().startswith(b"%PDF")


def test_long_label_reaches_the_measurement_callbacks():
    """A long label is what keeps the string a rope when it is passed to a text-measurement callback."""
    label = " ".join([f"{WORD} — ≥65 • étude"] * 40)
    svg = mermaidx.render(f'flowchart LR\n    A["{label}"] --> B[x]').svg()
    assert WORD in svg


def test_character_above_the_bmp_renders():
    """An emoji is a surrogate pair in a JS string, a different path from U+0100..U+FFFF. If this fails it
    may be a bug separate from #39: read the traceback before assuming the rope fix is incomplete."""
    svg = mermaidx.render('flowchart LR\n    A["launch 🚀 now"] --> B[x]').svg()
    assert "🚀" in svg


def test_parse_error_text_is_mermaids_own_error():
    """The error text crosses into Python too (__renderError). A long message holding characters above U+00FF
    used to be a rope there, so the caller got a binding TypeError instead of mermaid's own parse error.
    Diagram.svg() reports it as a RuntimeError chained from the engine's MermaidRenderError."""
    label = " ".join([f"{WORD} — ≥65 • étude"] * 40)
    with pytest.raises(RuntimeError, match="Parse error") as excinfo:
        mermaidx.render(f"flowchart LR\n    A[{label} --> B").svg()
    assert isinstance(excinfo.value.__cause__, MermaidRenderError)


class TestFlatHelper:
    """The JS helper on its own, so a change to it cannot go unnoticed just because the diagrams above no
    longer happen to produce a rope."""

    @pytest.fixture
    def ctx(self):
        context = quickjs.Context()
        context.eval(_FLATTEN_JS + " 0")
        return context

    def test_flattens_a_rope(self, ctx):
        ctx.eval("var r = ''; for (var i = 0; i < 2000; i++) r = r + '<t>— ' + i + '</t>'; 0")
        with pytest.raises(TypeError, match="Unknown quickjs tag"):
            ctx.eval("r")  # still a rope: the helper is needed
        assert len(ctx.eval("__flat(r)")) == len(ctx.eval("JSON.stringify(r)")) - 2

    @pytest.mark.parametrize(
        "expression, expected",
        [
            ("''", ""),
            ("42", 42),
            ("true", True),
            ("null", None),
            ("undefined", None),
        ],
    )
    def test_passes_other_values_through(self, ctx, expression, expected):
        assert ctx.eval(f"__flat({expression})") == expected

    def test_passes_objects_through_untouched(self, ctx):
        assert ctx.eval("JSON.stringify(__flat({a: [1, 2]}))") == '{"a":[1,2]}'


@pytest.mark.skipif(not HAS_V8, reason="the v8 backend needs the optional mini-racer package")
@pytest.mark.parametrize("kind", ["flowchart", "sequence"])
def test_text_renders_the_same_on_v8(kind):
    """The v8 engine never had the rope problem; this keeps the two backends in step."""
    svg = mermaidx.render(source(kind), backend="v8").svg()
    assert WORD in svg
