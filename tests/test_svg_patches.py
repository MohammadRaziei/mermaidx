"""Tests for mermaidx.engines._svg_patches -- the post-render SVG fixups
shared by the quickjs and v8 engines.
"""

from __future__ import annotations

import pytest

from mermaidx.engines._svg_patches import patch_mindmap_centering

quickjs = pytest.importorskip("quickjs")

import mermaidx

MINDMAP_STYLE_SVG = (
    '<svg><style>.section-root{fill:red;}</style>'
    '<g class="section-root"><text>leaf</text></g></svg>'
)


def test_patch_mindmap_centering_inserts_rule_when_section_root_present():
    """The centering rule should land right after the opening <style> tag,
    scoped to `.section-root .label text`."""
    patched = patch_mindmap_centering(MINDMAP_STYLE_SVG)
    assert ".section-root .label text{text-anchor:middle;}" in patched
    # inserted immediately after the *opening* <style ...> tag, not appended
    # somewhere else in the document
    assert patched.index(".section-root .label text") < patched.index("<g class")


def test_patch_mindmap_centering_is_noop_without_section_root():
    """Non-mindmap diagrams (no `section-root` class, or no <style> block
    at all) must pass through completely unchanged -- this patch is
    scoped to mindmap output only."""
    plain = "<svg><g><text>hello</text></g></svg>"
    assert patch_mindmap_centering(plain) == plain

    styled_no_section_root = "<svg><style>.foo{fill:red;}</style></svg>"
    assert patch_mindmap_centering(styled_no_section_root) == styled_no_section_root


def test_mindmap_render_is_centered_end_to_end():
    """Full mermaidx.render() path: a real mindmap diagram's rendered SVG
    must carry the centering rule mermaid's own CSS class-based rule
    never actually reaches (see patch_mindmap_centering's docstring).
    """
    code = "mindmap\n  root((mindmap))\n    Origins\n      Long history\n"
    svg = mermaidx.render(code).svg()
    assert "section-root" in svg
    assert ".section-root .label text{text-anchor:middle;}" in svg
