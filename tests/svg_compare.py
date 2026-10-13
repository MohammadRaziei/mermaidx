"""Element-by-element comparison of two SVG documents, parsed with pygixml.

Two documents are the same when they have exactly the same nodes in the same order -- elements (tag and
attributes, order aside), text (whitespace-only text too), CDATA, comments, processing instructions, and
whatever stands outside the root element -- with nothing more or less on either side. Only numbers get a
tolerance: every number inside an attribute value, a text node or a comment is approximately equal. A value is
split into its numbers and the text around them: the text must match exactly, the numbers within
`rel_tol` / `abs_tol` (so `d="M91.346875 10"` and `d="M91.34687690734863 10"` agree, `fill: red` and
`fill: blue` do not). A value that is base64-encoded JSON (mermaid's `data-points`) is decoded and compared the
same way, number by number.

The default tolerance is one LayoutUnit -- 1/64 px, the grain a browser lays text out on -- plus a hair: a
width may differ from Chrome's by that much because Chrome rounds every text run up to it. Anything beyond
is a real difference.
"""
from __future__ import annotations

import base64
import binascii
import json
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
DEFAULT_ABS_TOL = 0.02  # 1/64 = 0.015625


class Element:
    __slots__ = ("tag", "attrs", "children", "before", "after")

    def __init__(self, tag: str, attrs: dict, children: list):
        self.tag = tag
        self.attrs = attrs
        self.children = children  # Element | Leaf, in document order
        self.before = ""  # root only: the text ahead of the root element (prolog, comments, whitespace)
        self.after = ""   # root only: the text behind it


class Leaf:
    """A node that is not an element: its kind ("text", "cdata", "comment", "pi") and its text."""
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: str):
        self.kind = kind
        self.value = value


# Keep every node and every character: no whitespace dropping, no attribute whitespace normalisation (the
# defaults of an XML parser), only entity decoding and end-of-line normalisation, which XML itself requires.
_PARSE = (pygixml.ParseFlags.ESCAPES | pygixml.ParseFlags.EOL | pygixml.ParseFlags.CDATA
          | pygixml.ParseFlags.COMMENTS | pygixml.ParseFlags.PI | pygixml.ParseFlags.WS_PCDATA)
_KINDS = {"pcdata": "text", "cdata": "cdata", "comment": "comment", "pi": "pi"}


def parse(svg: str) -> Element:
    doc = pygixml.XMLDocument()
    if not doc.load_string(svg, _PARSE):  # pygixml reports a parse error as False and still hands back a partial tree
        raise ValueError("not well-formed XML: " + svg[:80].replace("\n", " "))
    node = doc.first_child()  # doc.root is the first node of any kind (a comment ahead of the root, say)
    while node is not None and not node.is_null() and node.type != "element":
        node = node.next_sibling
    root = _element(node)
    # What stands outside the root element is compared as text: prolog, comments, whitespace.
    start = svg.index("<" + root.tag)
    close = "</" + root.tag + ">"
    end = svg.rindex(close) + len(close) if close in svg else svg.index("/>", start) + 2
    root.before, root.after = svg[:start], svg[end:]
    return root


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
        elif child.type in _KINDS:
            kind, text = _KINDS[child.type], child.value or ""
            if children and isinstance(children[-1], Leaf) and children[-1].kind == kind == "text":
                children[-1].value += text
            else:
                children.append(Leaf(kind, text))
        child = child.next_sibling
    return Element(node.name, attrs, children)


def _decode_json(value: str):
    """The JSON a base64 attribute value encodes, or None if it is not that (an id that merely looks like it).
    b64decode(validate=True) already insists on the alphabet, the padding and a length multiple of four."""
    try:
        return json.loads(base64.b64decode(value, validate=True).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _same_json(a, b, rel_tol: float, abs_tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        if isinstance(a, dict) and isinstance(b, dict):
            return a.keys() == b.keys() and all(_same_json(a[k], b[k], rel_tol, abs_tol) for k in a)
        if isinstance(a, list) and isinstance(b, list):
            return len(a) == len(b) and all(_same_json(x, y, rel_tol, abs_tol) for x, y in zip(a, b))
        return type(a) is type(b) and a == b
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def _same_value(a: str, b: str, rel_tol: float, abs_tol: float) -> bool:
    if a == b:
        return True
    json_a = _decode_json(a)
    if json_a is not None:
        json_b = _decode_json(b)
        return json_b is not None and _same_json(json_a, json_b, rel_tol, abs_tol)
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
    for where, x, y in (("before the root", a.before, b.before), ("after the root", a.after, b.after)):
        if not _same_value(x, y, rel_tol, abs_tol):
            diffs.append(f"{where}: {x!r} != {y!r}")
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
        if isinstance(ca, Leaf) or isinstance(cb, Leaf):
            if not (isinstance(ca, Leaf) and isinstance(cb, Leaf)):
                diffs.append(f"{path}: child {i} is a node of another kind (element / text / comment ...) in the other")
            elif ca.kind != cb.kind:
                diffs.append(f"{path}: child {i} is {ca.kind} in one and {cb.kind} in the other")
            elif not _same_value(ca.value, cb.value, rel_tol, abs_tol):
                diffs.append(f"{path}: {ca.kind} {ca.value!r} != {cb.value!r}")
        else:
            _compare(ca, cb, _label(ca, path, i), rel_tol, abs_tol, diffs, limit)
