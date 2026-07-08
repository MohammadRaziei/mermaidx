"""Tests for mmdc.render_ascii (optional, backed by termaid)."""

from __future__ import annotations

import pytest

import mmdc

SIMPLE = "graph LR\nA-->B"


def test_render_ascii_basic():
    pytest.importorskip("termaid")
    art = mmdc.render_ascii(SIMPLE)
    assert isinstance(art, str)
    assert "A" in art and "B" in art


def test_render_ascii_use_ascii_option():
    pytest.importorskip("termaid")
    art = mmdc.render_ascii(SIMPLE, use_ascii=True)
    # pure-ASCII mode shouldn't contain Unicode box-drawing characters
    assert not any(ch in art for ch in "┌┐└┘│─►")


def test_render_ascii_without_termaid_raises_clear_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "termaid", None)
    with pytest.raises(ImportError, match=r"mmdc\[ascii\]"):
        mmdc.render_ascii(SIMPLE)
