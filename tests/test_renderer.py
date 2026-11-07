"""mermaidx.Renderer: workers with a lifetime of their own (threads by default, processes on request)."""

from __future__ import annotations

import gc
import threading
from pathlib import Path

import pytest

import mermaidx
from mermaidx import diagram as diagram_module
from mermaidx import renderer as renderer_module

SAMPLES = Path(__file__).parent / "samples"
PELE = {"backend": "js:pele"}


def _sources(count: int = 6) -> list[str]:
    return [f"graph LR\nA{i}-->B{i}" for i in range(count)]


def _threads(prefix: str) -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith(prefix)]


def _cached(d) -> bool:
    return ("svg", ()) in d._cache


# -- it renders what a plain render() renders ----------------------------------------------------------------------------


def test_renders_in_parallel_what_a_plain_render_renders_pele():
    sources = _sources(8)
    expected = [mermaidx.render(s, **PELE).svg() for s in sources]
    with mermaidx.Renderer(workers=3, **PELE) as renderer:
        assert [d.svg() for d in renderer.render_many(sources)] == expected


@pytest.mark.parametrize("name", ["01_simple_flowchart", "03_simple_sequence", "12_pie_chart", "13_gantt"])
def test_renders_in_parallel_what_a_plain_render_renders_mermaid(name):
    """mermaid.js: the same bytes as one diagram at a time in the shared engine (these four are drawn the same every time)."""
    source = (SAMPLES / f"{name}.mmd").read_text(encoding="utf-8")
    expected = mermaidx.render(source).svg()
    with mermaidx.Renderer(workers=2) as renderer:
        assert renderer.render(source).svg() == expected


def test_the_results_come_back_in_order_and_already_rendered():
    sources = _sources(12)
    with mermaidx.Renderer(workers=4, **PELE) as renderer:
        diagrams = renderer.render_many(sources)
    assert all(_cached(d) for d in diagrams)
    for i, d in enumerate(diagrams):
        assert f"A{i}" in d.svg() and f"B{i}" in d.svg()


def test_it_can_be_used_again_and_again_and_by_several_callers_at_once():
    results: dict[int, list] = {}
    with mermaidx.Renderer(workers=3, **PELE) as renderer:
        assert len(renderer.render_many(_sources(3))) == 3
        assert len(renderer.render_many(_sources(5))) == 5

        def call(n):
            results[n] = renderer.render_many([f"graph LR\nX{n}k{i}-->Y" for i in range(4)])

        callers = [threading.Thread(target=call, args=(n,)) for n in range(4)]
        for t in callers:
            t.start()
        for t in callers:
            t.join()
    for n, diagrams in results.items():
        for i, d in enumerate(diagrams):
            assert f"X{n}k{i}" in d.svg()


def test_empty_input_and_generators_and_forwarded_options():
    with mermaidx.Renderer(workers=2, **PELE) as renderer:
        assert renderer.render_many([]) == []
        assert len(renderer.render_many(s for s in _sources(3))) == 3
    with mermaidx.Renderer(workers=2, theme="dark") as renderer:
        assert renderer.render("graph LR\nA-->B").svg().startswith("<svg")


def test_a_diagram_that_fails_comes_back_unrendered_and_raises_on_svg():
    with mermaidx.Renderer(workers=2, **PELE) as renderer:
        bad, good = renderer.render_many(["this is not a valid mermaid diagram {{{", "graph LR\nA-->B"])
    assert not _cached(bad) and _cached(good)
    with pytest.raises(RuntimeError):
        bad.svg()


# -- every worker has an engine of its own -------------------------------------------------------------------------------


def test_every_worker_thread_has_its_own_engine_and_the_shared_ones_are_left_alone():
    shared_before = dict(diagram_module._engines)
    with mermaidx.Renderer(workers=3, **PELE) as renderer:
        engines = [e for registry in renderer._backend._registries for e in registry.values()]
        assert len(engines) == 3 and len({id(e) for e in engines}) == 3
        assert all(e.started for e in engines)
        renderer.render_many(_sources(6))
        assert diagram_module._engines == shared_before
    assert not any(e.started for e in engines)


def test_work_is_spread_over_the_workers():
    """Four slow-ish diagrams on four workers: each worker's engine rendered at least one."""
    with mermaidx.Renderer(workers=4) as renderer:
        engines = [e for registry in renderer._backend._registries for e in registry.values()]
        renders_before = [e._render_count for e in engines]
        renderer.render_many([f"graph LR\nA{i}-->B{i}-->C{i}-->D{i}" for i in range(16)])
        done = [e._render_count - before for e, before in zip(engines, renders_before)]
    assert sum(done) == 16 and min(done) >= 1


# -- the lifetime is the with block ---------------------------------------------------------------------------------------


def test_workers_are_running_inside_the_block_and_gone_after_it():
    engine_threads_before = len(_threads("mermaidx-engine"))
    with mermaidx.Renderer(workers=3, **PELE) as renderer:
        assert len(_threads("mermaidx-renderer-")) == 3
        assert not renderer.closed
    assert renderer.closed
    assert not _threads("mermaidx-renderer-")
    assert len(_threads("mermaidx-engine")) == engine_threads_before


def test_close_is_idempotent_and_a_closed_renderer_refuses_work():
    renderer = mermaidx.Renderer(workers=2, **PELE)
    renderer.render("graph LR\nA-->B")
    renderer.close()
    renderer.close()
    with pytest.raises(RuntimeError, match="closed"):
        renderer.render("graph LR\nA-->B")
    with pytest.raises(RuntimeError, match="closed"):
        renderer.render_many(["graph LR\nA-->B"])


def test_an_exception_inside_the_block_still_stops_the_workers():
    key = "boom"
    with pytest.raises(KeyError), mermaidx.Renderer(workers=2, **PELE) as renderer:
        raise KeyError(key)
    assert renderer.closed and not _threads("mermaidx-renderer-")


def test_a_renderer_dropped_without_close_is_cleaned_up_by_its_finalizer():
    renderer = mermaidx.Renderer(workers=2, **PELE)
    threads = list(renderer._backend._threads)
    engines = [e for registry in renderer._backend._registries for e in registry.values()]
    del renderer
    gc.collect()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads)
    assert not any(e.started for e in engines)


def test_starting_workers_leaves_the_thread_stack_size_as_it_was():
    """Engines are started from several threads at once, and threading.stack_size() is process-wide."""
    before = threading.stack_size()
    with mermaidx.Renderer(workers=4, **PELE):
        assert threading.stack_size() == before
    assert threading.stack_size() == before


# -- bad arguments fail at once, leaving nothing running -------------------------------------------------------------------


def test_options_no_diagram_takes_raise_before_any_worker_starts():
    with pytest.raises(ValueError, match="backend"):
        mermaidx.Renderer(workers=2, backend="js:nonexistent")
    assert not _threads("mermaidx-renderer-")


def test_unknown_executor_and_too_few_workers_are_refused():
    with pytest.raises(ValueError, match="executor"):
        mermaidx.Renderer(executor="coroutine")
    with pytest.raises(ValueError, match="at least 1"):
        mermaidx.Renderer(workers=0)


def test_an_engine_that_cannot_start_raises_in_the_constructor_and_stops_what_started(monkeypatch):
    calls = []

    def failing_warm(opts):
        calls.append(1)
        if len(calls) == 2:
            message = "no such engine"
            raise ImportError(message)
        renderer_module.Diagram("graph LR\nA-->B", **opts)

    monkeypatch.setattr(renderer_module, "_warm", failing_warm)
    with pytest.raises(ImportError, match="no such engine"):
        mermaidx.Renderer(workers=3, **PELE)
    assert not _threads("mermaidx-renderer-")


# -- processes ----------------------------------------------------------------------------------------------------------------


def test_process_workers_render_the_same_and_are_stopped_by_close():
    sources = _sources(6)
    expected = [mermaidx.render(s, **PELE).svg() for s in sources]
    with mermaidx.Renderer(workers=2, executor="process", **PELE) as renderer:
        processes = list(renderer._backend._pool._pool)
        assert len(processes) == 2 and all(p.is_alive() for p in processes)
        assert [d.svg() for d in renderer.render_many(sources)] == expected
        assert renderer.executor == "process"
    assert not any(p.is_alive() for p in processes)
    assert renderer.closed


def test_repr_says_what_it_is():
    with mermaidx.Renderer(workers=2, **PELE) as renderer:
        assert repr(renderer) == "<Renderer thread x2 running>"
    assert repr(renderer) == "<Renderer thread x2 closed>"
