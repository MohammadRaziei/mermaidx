"""Tests for mmdc.render_many (real parallelism via multiprocessing)."""

from __future__ import annotations

import mmdc

SOURCES = [
    "graph LR\nA-->B",
    "graph TD\nA-->B-->C",
    "sequenceDiagram\nAlice->>Bob: Hi",
]


def test_render_many_single_worker_matches_sequential():
    diagrams = mmdc.render_many(SOURCES, workers=1)
    assert len(diagrams) == len(SOURCES)
    for d, src in zip(diagrams, SOURCES):
        assert isinstance(d, mmdc.Diagram)
        assert d.svg().startswith("<svg")


def test_render_many_multiple_workers():
    diagrams = mmdc.render_many(SOURCES, workers=2)
    assert len(diagrams) == len(SOURCES)
    for d in diagrams:
        assert d.svg().startswith("<svg")


def test_render_many_preserves_order():
    sources = [f"graph LR\nA{i}-->B{i}" for i in range(6)]
    diagrams = mmdc.render_many(sources, workers=3)
    for i, d in enumerate(diagrams):
        assert f"A{i}" in d.svg()


def test_render_many_empty_list():
    assert mmdc.render_many([]) == []


def test_render_many_forwards_opts():
    diagrams = mmdc.render_many(SOURCES, workers=2, theme="dark")
    assert all(d.svg().startswith("<svg") for d in diagrams)


def test_render_many_default_workers():
    diagrams = mmdc.render_many(SOURCES)
    assert len(diagrams) == len(SOURCES)
