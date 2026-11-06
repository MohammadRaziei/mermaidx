"""Tests for mermaidx.render_many (real parallelism via multiprocessing)."""

from __future__ import annotations

import os

import pytest

import mermaidx
from mermaidx import pool

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


# -- the pool outlives the call ----------------------------------------------------------------------------------------


@pytest.fixture
def clean_pool():
    mermaidx.shutdown_pool()
    yield
    mermaidx.shutdown_pool()


def _pids():
    assert pool._shared is not None, "no pool is running"
    return sorted(p.pid for p in pool._shared.pool._pool)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.mark.usefixtures("clean_pool")
def test_the_next_call_uses_the_workers_the_last_one_left():
    mermaidx.render_many(SOURCES, workers=2)
    first = _pids()
    assert len(first) == 2
    diagrams = mermaidx.render_many(SOURCES, workers=2)
    assert _pids() == first
    assert all(_svg_is_cached(d) for d in diagrams)


@pytest.mark.usefixtures("clean_pool")
def test_another_number_of_workers_starts_another_pool_and_stops_the_old_one():
    mermaidx.render_many(SOURCES, workers=2)
    old = _pids()
    mermaidx.render_many(SOURCES, workers=3)
    new = _pids()
    assert len(new) == 3 and not set(new) & set(old)
    assert not any(_alive(pid) for pid in old)


@pytest.mark.usefixtures("clean_pool")
def test_reuse_pool_false_leaves_nothing_running():
    diagrams = mermaidx.render_many(SOURCES, workers=2, reuse_pool=False)
    assert all(_svg_is_cached(d) for d in diagrams)
    assert pool._shared is None


@pytest.mark.usefixtures("clean_pool")
def test_reuse_pool_false_does_not_touch_the_shared_pool():
    mermaidx.render_many(SOURCES, workers=2)
    shared = _pids()
    mermaidx.render_many(SOURCES, workers=3, reuse_pool=False)
    assert _pids() == shared and all(_alive(pid) for pid in shared)


@pytest.mark.usefixtures("clean_pool")
def test_shutdown_pool_stops_the_workers_and_the_next_call_starts_new_ones():
    mermaidx.render_many(SOURCES, workers=2)
    old = _pids()
    mermaidx.shutdown_pool()
    assert pool._shared is None and not any(_alive(pid) for pid in old)
    mermaidx.shutdown_pool()  # nothing to stop is fine
    assert all(_svg_is_cached(d) for d in mermaidx.render_many(SOURCES, workers=2))
    assert not set(_pids()) & set(old)


@pytest.mark.usefixtures("clean_pool")
def test_a_call_that_needs_another_size_while_the_pool_is_busy_gets_a_pool_of_its_own():
    busy = pool._checkout(2)  # as if another thread were in the middle of a render_many(workers=2)
    try:
        diagrams = mermaidx.render_many(SOURCES, workers=3)
        assert all(_svg_is_cached(d) for d in diagrams)
        assert pool._shared is busy and busy.in_flight == 1 and busy.workers == 2
    finally:
        pool._release(busy)
    assert pool._shared.in_flight == 0


@pytest.mark.usefixtures("clean_pool")
def test_a_pool_inherited_by_fork_is_left_to_the_parent_and_a_new_one_is_made():
    mermaidx.render_many(SOURCES, workers=2)
    parent_pool = pool._shared
    parent_pids = _pids()
    parent_pool.pid = -1  # what a forked child sees: a pool made by a process that is not this one
    try:
        mermaidx.render_many(SOURCES, workers=2)
        assert pool._shared is not parent_pool
        assert all(_alive(pid) for pid in parent_pids)  # not stopped by the "child"
    finally:
        parent_pool.pid = os.getpid()
        pool._stop(parent_pool)


@pytest.mark.usefixtures("clean_pool")
def test_a_call_that_fails_does_not_leave_its_tasks_running():
    mermaidx.render_many(SOURCES, workers=2)
    with pytest.raises(Exception):  # noqa: B017 -- the options cannot be sent to a worker
        mermaidx.render_many(SOURCES, workers=2, config={"unpicklable": lambda: 1})
    assert pool._shared is None
    assert all(_svg_is_cached(d) for d in mermaidx.render_many(SOURCES, workers=2))
