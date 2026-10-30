"""Tests for mermaidx.render_many (real parallelism via multiprocessing)."""

from __future__ import annotations

import pytest

import mermaidx

SOURCES = [
    "graph LR\nA-->B",
    "graph TD\nA-->B-->C",
    "sequenceDiagram\nAlice->>Bob: Hi",
]


def test_render_many_single_worker_matches_sequential():
    diagrams = mermaidx.render_many(SOURCES, workers=1)
    assert len(diagrams) == len(SOURCES)
    for d, src in zip(diagrams, SOURCES):
        assert isinstance(d, mermaidx.Diagram)
        assert d.svg().startswith("<svg")


def test_render_many_multiple_workers():
    diagrams = mermaidx.render_many(SOURCES, workers=2)
    assert len(diagrams) == len(SOURCES)
    for d in diagrams:
        assert d.svg().startswith("<svg")


def test_render_many_preserves_order():
    sources = [f"graph LR\nA{i}-->B{i}" for i in range(6)]
    diagrams = mermaidx.render_many(sources, workers=3)
    for i, d in enumerate(diagrams):
        assert f"A{i}" in d.svg()


def test_render_many_empty_list():
    assert mermaidx.render_many([]) == []


def test_render_many_forwards_opts():
    diagrams = mermaidx.render_many(SOURCES, workers=2, theme="dark")
    assert all(d.svg().startswith("<svg") for d in diagrams)


def test_render_many_default_workers():
    diagrams = mermaidx.render_many(SOURCES)
    assert len(diagrams) == len(SOURCES)


def _svg_is_cached(d) -> bool:
    return ("svg", ()) in d._cache


@pytest.mark.parametrize("workers", [1, 2])
def test_render_many_renders_the_svg_before_returning(workers):
    """https://github.com/MohammadRaziei/mermaidx/issues/43 -- render_many() used to return lazy, unrendered
    diagrams, so the rendering happened later, one diagram after another, in the caller's process."""
    diagrams = mermaidx.render_many(SOURCES, workers=workers)
    assert all(_svg_is_cached(d) for d in diagrams)


def test_render_many_returns_a_failed_diagram_unrendered_and_it_raises_on_svg():
    diagrams = mermaidx.render_many(["this is not a valid mermaid diagram {{{", SOURCES[0]], workers=2)
    assert not _svg_is_cached(diagrams[0]) and _svg_is_cached(diagrams[1])
    assert diagrams[1].svg().startswith("<svg")
    with pytest.raises(RuntimeError):
        diagrams[0].svg()


def test_render_many_other_formats_are_made_from_the_rendered_svg():
    d = mermaidx.render_many(SOURCES[:2], workers=2)[0]
    assert d.png()[:8] == b"\x89PNG\r\n\x1a\n"
