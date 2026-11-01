"""The ELK layout (issue #33): `flowchart-elk` and `layout: elk` used to fall back to dagre without a word, because
mermaid.js only knows ELK once `registerLayoutLoaders` has been called. mermaidx now evaluates assets/layout_elk.js
for a diagram that asks for it, and only for that one (it is 2.4 MB)."""
import re

import pytest

import mermaidx
from mermaidx.engines import _common

FLOWCHART = """{head}
  A([Start]) ==> B[Step 1]
  B ==> C{{Flow 1}}
  C -- Choice 1.1 --> D[Step 2.1]
  C -- Choice 1.3 --> I[Step 2.3]
  C == Choice 1.2 ==> E[Step 2.2]
  D --> F{{Flow 2}}
  E ==> F
  F == Choice 2.1 ==> H[Feedback node]
  H ==> B
  F == Choice 2.2 ==> G((Finish))
"""
DAGRE = FLOWCHART.format(head="flowchart TD")
ELK = FLOWCHART.format(head="flowchart-elk TD")
ELK_FRONTMATTER = "---\nconfig:\n  layout: elk\n---\n" + DAGRE


def _height(svg: str) -> float:
    return float(re.search(r'viewBox="[\d.\-]+ [\d.\-]+ [\d.]+ ([\d.]+)"', svg).group(1))


@pytest.mark.parametrize(
    "code, config, expected",
    [
        (DAGRE, None, False),
        (ELK, None, True),
        (ELK_FRONTMATTER, None, True),
        ('%%{init: {"layout": "elk"}}%%\n' + DAGRE, None, True),
        ("flowchart TD\n  A --> B", {"layout": "elk"}, True),
        ("flowchart TD\n  A --> B", {"layout": "elk.stress"}, True),
        ("flowchart TD\n  A --> B", {"layout": "dagre"}, False),
        ("flowchart TD\n  A[Elkhound] --> B[elkjs]", None, False),  # the word, not a prefix of another word
    ],
)
def test_needs_elk(code, config, expected):
    assert _common.needs_elk(code, config) is expected


def test_elk_script_is_only_part_of_the_render_script_of_a_diagram_that_needs_it():
    plain = _common.render_script(DAGRE, None, None, None)
    with_elk = _common.render_script(ELK, None, None, None)
    assert "@mermaid-js/layout-elk" not in plain and len(plain) < 20_000
    assert len(with_elk) > 2_000_000
    assert with_elk.startswith("/* @mermaid-js/layout-elk")  # the ELK script comes first, then the usual one
    assert with_elk.rstrip().endswith(".catch(e => { globalThis.__renderError = (e && e.name ? e.name + ': ' + e.message : String(e)); });")


def test_elk_scripts_are_not_part_of_the_context_every_render_starts_from():
    assert not any("@mermaid-js/layout-elk" in script for script in _common.context_scripts("mermaid"))


def test_pele_ignores_the_request_and_never_gets_the_elk_script():
    assert "@mermaid-js/layout-elk" not in _common.render_script(ELK, None, None, None, library="pele")


@pytest.mark.parametrize("engine", ["quickjs", "v8"])
def test_flowchart_elk_is_laid_out_by_elk_not_by_dagre(engine):
    if engine == "v8":
        pytest.importorskip("py_mini_racer")
    dagre = mermaidx.render(DAGRE, engine=engine).svg()
    elk = mermaidx.render(ELK, engine=engine).svg()
    # ELK routes the feedback edge around the side and spreads the layers differently: another height
    assert _height(elk) != _height(dagre)
    # `layout: elk` in the frontmatter gives the same drawing as the `flowchart-elk` keyword
    assert _height(mermaidx.render(ELK_FRONTMATTER, engine=engine).svg()) == _height(elk)


def test_a_diagram_after_an_elk_one_is_dagre_again():
    # every render starts from a fresh context, so the ELK registration of one render does not leak into the next
    before = _height(mermaidx.render(DAGRE).svg())
    mermaidx.render(ELK).svg()
    assert _height(mermaidx.render(DAGRE).svg()) == before
