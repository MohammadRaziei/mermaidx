"""Element-by-element comparison of two SVG documents, parsed with pygixml.

Two documents are the same when they have the same elements in the same order (tag, attributes -- order
aside --, text), and every number inside an attribute value or a text node is approximately equal. A value is
split into its numbers and the text around them: the text must match exactly, the numbers within
`rel_tol` / `abs_tol` (so `d="M91.346875 10"` and `d="M91.34687690734863 10"` agree, `fill: red` and
`fill: blue` do not).
"""
from __future__ import annotations

import math
import re

import pygixml

# Ids mermaid.js generates from Math.random() / a hash on every run, in mmdc as much as in mermaidx:
#   state diagrams:  <svg-id>-state-id-<random>-<n>   (mermaid's generateId)
#   architecture:    IconifyId<random hex>             (the icon renderer's own id)
RANDOM_IDS = [
    (re.compile(r"(state-id)-[0-9a-z]+-"), r"\1-#-"),
    (re.compile(r"IconifyId[0-9a-f]+"), "IconifyId#"),
]


def mask_random_ids(svg: str) -> str:
    for pattern, replacement in RANDOM_IDS:
        svg = pattern.sub(replacement, svg)
    return svg


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

DEFAULT_REL_TOL = 1e-4
DEFAULT_ABS_TOL = 1e-3


class Element:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict, children: list):
        self.tag = tag
        self.attrs = attrs
        self.children = children  # Element | str (text), in document order


def parse(svg: str) -> Element:
    doc = pygixml.XMLDocument()
    if not doc.load_string(svg):  # pygixml reports a parse error as False and still hands back a partial tree
        raise ValueError("not well-formed XML: " + svg[:80].replace("\n", " "))
    return _element(doc.root)


def _element(node) -> Element:
    attrs = {}
    attr = node.first_attribute()
    while attr is not None and attr.name:
        attrs[attr.name] = attr.value
        attr = attr.next_attribute

    children: list = []
    child = node.first_child()
    while child is not None and not child.is_null():
        if child.type == "element":
            children.append(_element(child))
        elif child.type in ("pcdata", "cdata"):
            text = child.value or ""
            if children and isinstance(children[-1], str):
                children[-1] += text
            else:
                children.append(text)
        child = child.next_sibling
    return Element(node.name, attrs, children)


def _same_value(a: str, b: str, rel_tol: float, abs_tol: float) -> bool:
    if a == b:
        return True
    if _NUMBER.split(a) != _NUMBER.split(b):
        return False
    nums_a, nums_b = _NUMBER.findall(a), _NUMBER.findall(b)
    return len(nums_a) == len(nums_b) and all(
        math.isclose(float(x), float(y), rel_tol=rel_tol, abs_tol=abs_tol) for x, y in zip(nums_a, nums_b)
    )


def compare(a: Element, b: Element, *, rel_tol: float = DEFAULT_REL_TOL, abs_tol: float = DEFAULT_ABS_TOL,
            limit: int = 50) -> list[str]:
    """Differences between two parsed documents, each as a readable line with the element's place."""
    diffs: list[str] = []
    _compare(a, b, a.tag, rel_tol, abs_tol, diffs, limit)
    return diffs


def _label(el: Element, path: str, index: int) -> str:
    ident = el.attrs.get("id")
    return f"{path}/{el.tag}[{index}]" + (f"#{ident}" if ident else "")


def _compare(a: Element, b: Element, path: str, rel_tol: float, abs_tol: float, diffs: list, limit: int) -> None:
    if len(diffs) >= limit:
        return
    if a.tag != b.tag:
        diffs.append(f"{path}: tag {a.tag!r} != {b.tag!r}")
        return

    for name in sorted(set(a.attrs) | set(b.attrs)):
        if name not in a.attrs:
            diffs.append(f"{path}: attribute {name!r} only in the second ({b.attrs[name]!r})")
        elif name not in b.attrs:
            diffs.append(f"{path}: attribute {name!r} only in the first ({a.attrs[name]!r})")
        elif not _same_value(a.attrs[name], b.attrs[name], rel_tol, abs_tol):
            diffs.append(f"{path}: {name}: {a.attrs[name]!r} != {b.attrs[name]!r}")

    if len(a.children) != len(b.children):
        diffs.append(f"{path}: {len(a.children)} children != {len(b.children)}")
        return
    for i, (ca, cb) in enumerate(zip(a.children, b.children)):
        if isinstance(ca, str) or isinstance(cb, str):
            if not (isinstance(ca, str) and isinstance(cb, str)):
                diffs.append(f"{path}: child {i} is text in one and an element in the other")
            elif not _same_value(ca, cb, rel_tol, abs_tol):
                diffs.append(f"{path}: text {ca!r} != {cb!r}")
        else:
            _compare(ca, cb, _label(ca, path, i), rel_tol, abs_tol, diffs, limit)
