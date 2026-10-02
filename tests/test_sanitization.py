"""mermaid.render() ends with DOMPurify.sanitize(); inside the DOM shim it has to actually run.

DOMPurify turns itself off (isSupported = false) when the page lacks an HTML parser, NodeFilter /
NodeIterator and a few DOM interfaces -- in which case sanitize() silently returns its input and
dangerous markup survives into the SVG. These tests fail if that ever happens again.
"""
import re

import pytest

import mermaidx


@pytest.mark.parametrize("label, forbidden", [
    ('<b onclick=alert(2)>bold</b>', "onclick"),
    ('a<script>alert(1)</script>b', "<script"),
])
def test_dangerous_markup_is_stripped(label, forbidden):
    svg = mermaidx.render(f'flowchart LR\n    A["{label}"]\n').svg()
    assert forbidden not in svg


def test_layout_scratch_attributes_do_not_leak():
    """`label-offset-y` (cylinder), `text-height` (gantt) and `position` (journey) are attributes
    mermaid leaves on shapes while laying out; a browser's DOMPurify drops them from the output."""
    cyl = mermaidx.render('flowchart LR\n    A[("db")]\n').svg()
    gantt = mermaidx.render("gantt\n    dateFormat YYYY-MM-DD\n    section s\n    t :a, 2026-01-01, 3d\n").svg()
    journey = mermaidx.render("journey\n    title t\n    section s\n      step: 3: me\n").svg()
    assert "label-offset-y" not in cyl
    assert "text-height" not in gantt
    assert not re.search(r'\sposition="', journey)


def test_allowed_attributes_survive():
    svg = mermaidx.render("flowchart LR\n    A[start] --> B[end]\n").svg()
    assert 'viewBox="' in svg and 'role="graphics-document document"' in svg
    assert re.search(r'data-id="', svg) and "<foreignObject" in svg
