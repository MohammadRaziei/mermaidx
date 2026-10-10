"""The shim's selector engine, against what Chrome's querySelectorAll does.

mermaid.js leans on it: mermaidAPI.render calls `selectAll("foreignobject > *").attr("xmlns", ...)` on every
diagram, and Chrome matches that lower-case `foreignobject` against the SVG <foreignObject> element and
`>` against direct children only.
"""
import json

import pytest
from test_dom_shim import _make_ctx

MARKUP = (
    '<svg id="s">'
    '<foreignObject id="fo"><div id="outer"><div id="inner"></div></div><span id="sib"></span></foreignObject>'
    '<g id="g1"><rect id="r1"/><rect id="r2"/><text id="t1"/></g>'
    "</svg>"
)


def select(selector):
    ctx = _make_ctx()
    ctx.set("__markup", MARKUP)
    ctx.set("__selector", selector)
    return json.loads(ctx.eval(
        "document.body.innerHTML = __markup;"
        "JSON.stringify(Array.from(document.body.querySelectorAll(__selector)).map(e => e.getAttribute('id')));"
    ))


@pytest.mark.parametrize("selector, expected", [
    # type selectors match without regard to case, even for camelCase SVG names
    ("foreignobject", ["fo"]),
    ("FOREIGNOBJECT", ["fo"]),
    ("foreignObject", ["fo"]),
    # the child combinator reaches direct children only
    ("foreignobject > *", ["outer", "sib"]),
    ("foreignobject>*", ["outer", "sib"]),
    ('[id="fo"] > *', ["outer", "sib"]),
    ("svg > g > rect", ["r1", "r2"]),
    ("svg > rect", []),
    # the descendant combinator reaches all of them
    ("foreignobject *", ["outer", "inner", "sib"]),
    ("svg rect", ["r1", "r2"]),
    # sibling combinators
    ("rect + rect", ["r2"]),
    ("rect + text", ["t1"]),
    ("rect ~ text", ["t1"]),
    ("text + rect", []),
    ("g > rect:first-child", ["r1"]),
    # lists
    ("foreignobject, g", ["fo", "g1"]),
])
def test_selector(selector, expected):
    assert select(selector) == expected
