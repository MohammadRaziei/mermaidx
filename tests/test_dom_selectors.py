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


# __resolveCssProp narrows the rules to test by the element's tag, id and class before matching them. That has to give
# what testing every rule in the stylesheet gives, whatever the selectors look like and after the markup changed.
STYLE = (
    ".a{font-size:10px} #x{font-size:20px} g text{font-size:12px} g > .b{font-size:14px}"
    "text.a.b{font-weight:bold} rect:first-child{font-size:30px} [id=\"r2\"]{font-size:31px} *{font-family:Foo}"
    "g .a, #sib{font-family:Bar} .a:not(.b){font-weight:600} svg{font-size:9px} foreignobject div{font-size:8px}"
    "rect + rect{font-weight:700} .a.b{font-size:15px} text:nth-child(2){font-size:99px} .unused{font-size:77px}"
)
STYLED_MARKUP = (
    '<svg id="s"><g id="g1" class="a"><rect id="r1" class="a b"/><rect id="r2"/>'
    '<text id="t1" class="a b"/><text id="t2" class="b"/></g>'
    '<foreignObject id="fo"><div id="x" class="a"><div id="inner"/></div><span id="sib"/></foreignObject></svg>'
)
RESOLVE_ALL = """
(() => {
  const rules = __getCssRules();
  const props = ["font-size", "font-family", "font-weight", "fill"];
  const out = [];
  for (const el of document.body.querySelectorAll("*")) {
    for (const prop of props) {
      let all = null;                                    // every rule tested, the way it was done before the index
      for (const rule of rules) if (prop in rule.decls && __matches(el, rule.selectors)) all = rule.decls[prop];
      out.push([el.getAttribute("id"), prop, all, __resolveCssProp(el, prop)]);
    }
  }
  return JSON.stringify(out);
})()
"""


def test_css_lookup_by_index_equals_testing_every_rule():
    ctx = _make_ctx()
    ctx.set("__markup", STYLED_MARKUP)
    ctx.set("__style", STYLE)
    ctx.eval(
        "const st = document.createElement('style'); st.textContent = __style; document.body.appendChild(st);"
        "const host = document.createElement('div'); host.innerHTML = __markup; document.body.appendChild(host);"
    )
    before = json.loads(ctx.eval(RESOLVE_ALL))
    assert all(tested == indexed for _, _, tested, indexed in before)
    assert len({tested for _, _, tested, _ in before if tested}) > 5  # the stylesheet does reach the elements

    # the markup changes: an id, a class and a position move, and the lookup has to follow
    ctx.eval(
        "document.getElementById('r2').setAttribute('class', 'a');"
        "document.getElementById('t2').classList.add('a');"
        "const g = document.getElementById('g1'); g.insertBefore(document.getElementById('t1'), g.childNodes[0]);"
        "document.getElementById('sib').setAttribute('id', 'x');"
    )
    after = json.loads(ctx.eval(RESOLVE_ALL))
    assert all(tested == indexed for _, _, tested, indexed in after)
    assert after != before
