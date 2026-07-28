"""Tests for mermaidx.render_ascii (backed by termaid, a core dependency)."""

from __future__ import annotations

import mermaidx

SIMPLE = "graph LR\nA-->B"


def test_render_ascii_basic():
    art = mermaidx.render_ascii(SIMPLE)
    assert isinstance(art, str)
    assert "A" in art and "B" in art


def test_render_ascii_use_ascii_option():
    art = mermaidx.render_ascii(SIMPLE, use_ascii=True)
    # pure-ASCII mode shouldn't contain Unicode box-drawing characters
    assert not any(ch in art for ch in "┌┐└┘│─►")


def test_render_ascii_ends_with_trailing_newline():
    """https://github.com/MohammadRaziei/mermaidx/issues/32

    render_ascii() (and, via it, Diagram.ascii()/.save()) must end with a
    trailing newline, matching termaid's own CLI output and normal text-
    file convention -- termaid.render() itself doesn't include one.
    """
    code = (
        "timeline\n"
        "    title History of Social Media Platform\n"
        "    2002 : LinkedIn\n"
        "    2004 : Facebook\n"
        "         : Google\n"
        "    2005 : YouTube\n"
        "    2006 : Twitter\n"
    )
    assert mermaidx.render_ascii(code).endswith("\n")
    assert mermaidx.render_ascii(SIMPLE).endswith("\n")
    assert mermaidx.render_ascii(SIMPLE, use_ascii=True).endswith("\n")
