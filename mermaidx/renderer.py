"""
mermaidx.renderer -- rendering many diagrams in parallel, with a lifetime you can see.

    with mermaidx.Renderer(workers=4, theme="dark") as renderer:
        diagrams = renderer.render_many(sources)       # and again, and again: the workers stay ready

A Renderer starts its workers when it is made, each with the engine its diagrams render in already loaded (so the
cost of loading the JS library is paid there, once, and a bad option or a missing engine raises there), and stops them
when the ``with`` block ends or ``close()`` is called. Nothing outlives it: no pool is kept by the module, and nothing
runs at interpreter exit for a Renderer that was closed. (One that was not is closed by a finalizer, as a safety
net.)

Workers are threads by default (``executor="thread"``). Rendering is CPU-bound work inside a JS engine, which looks
like a case for processes, but it is not: the QuickJS binding gives the GIL back while JavaScript runs, and the V8
engine runs in a child process of its own, so threads that each have an engine of their own do overlap. A thread is
cheaper than a process in every way that matters here -- nothing is spawned, the engines are the only per-worker
memory, the bytecode and the fonts are in memory once, and no Diagram is pickled on its way back. An engine renders one
diagram at a time, so every worker thread gets an engine of its own (they are not the ones ``mermaidx.render()`` uses).

``executor="process"`` starts one process per worker instead (the 'spawn' method, so that no native state is inherited):
use it when a crash inside the JS engine must not take the caller down with it, or to measure the two against
each other.

The worker renders the SVG -- the expensive part -- before the Diagram goes back: a Diagram is lazy, and one returned
unrendered would be rendered later, one after another, in the caller's thread
(https://github.com/MohammadRaziei/mermaidx/issues/43).
"""

from __future__ import annotations

import contextlib
import multiprocessing as mp
import os
import queue
import threading
import weakref
from concurrent.futures import Future
from typing import Iterable

from .diagram import Diagram, _bind_engines, _get_engine

EXECUTORS = ("thread", "process")

# 'spawn' avoids inheriting any native (QuickJS/novasvg) state across fork(): each process starts completely fresh.
_CTX = mp.get_context("spawn")

# What a worker renders first to have its engine loaded: it draws nothing a caller sees.
_WARM_SOURCE = "flowchart LR\n  A-->B"


def _render_one(source: str, opts: dict) -> Diagram:
    d = Diagram(source, **opts)
    # Parse + layout, in this worker; the SVG is cached in `d` and goes back with it. A diagram that fails is left
    # uncached: the error then surfaces on the caller's own .svg(), and one bad diagram does not take the whole batch
    # down.
    with contextlib.suppress(Exception):
        d.svg()
    return d


def _warm(opts: dict) -> None:
    """Starts the engine the diagrams of `opts` render in, so it is ready before the first one."""
    d = Diagram(_WARM_SOURCE, **opts)
    _get_engine(d.engine, d._library)


# -- thread workers --------------------------------------------------------------------------------


class _Threads:
    """`workers` threads taking diagrams from one queue, each rendering in an engine of its own."""

    def __init__(self, workers: int, opts: dict) -> None:
        self._opts = opts
        self._tasks: queue.SimpleQueue = queue.SimpleQueue()
        self._registries: list[dict] = [{} for _ in range(workers)]  # the engines of each thread, closed by close()
        self._threads: list[threading.Thread] = []
        self._closed = False
        ready: list[Future] = []
        for number, registry in enumerate(self._registries):
            started: Future = Future()
            thread = threading.Thread(
                target=self._work, args=(registry, started), name=f"mermaidx-renderer-{number}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
            ready.append(started)
        try:
            for started in ready:
                started.result()  # raises what loading the engine raised
        except BaseException:
            self.close()
            raise

    def _work(self, registry: dict, started: Future) -> None:
        _bind_engines(registry)
        try:
            _warm(self._opts)
        except BaseException as error:  # handed to the thread that is waiting in __init__
            started.set_exception(error)
            return
        started.set_result(None)
        while True:
            task = self._tasks.get()
            if task is None:
                return
            future, source = task
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(_render_one(source, self._opts))
            except BaseException as error:  # handed to the thread that is waiting for the result
                future.set_exception(error)

    def run(self, sources: list[str]) -> list[Diagram]:
        futures: list[Future] = []
        for source in sources:
            future: Future = Future()
            futures.append(future)
            self._tasks.put((future, source))
        try:
            return [future.result() for future in futures]
        except BaseException:
            for future in futures:
                future.cancel()  # the ones not started yet; a running one finishes and is dropped
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # The stops come after every diagram already asked for, so those are rendered, not abandoned.
        for _ in self._threads:
            self._tasks.put(None)
        for thread in self._threads:
            thread.join()
        for registry in self._registries:
            for engine in registry.values():
                with contextlib.suppress(Exception):  # closing goes on with the other engines
                    engine.close()
            registry.clear()


# -- process workers -------------------------------------------------------------------------------


def _process_init(opts: dict) -> None:
    with contextlib.suppress(Exception):  # the same error comes back with every diagram
        _warm(opts)


def _process_render(args: tuple) -> Diagram:
    source, opts = args
    return _render_one(source, opts)


class _Processes:
    """`workers` processes, each with the engine its diagrams render in loaded when it starts."""

    def __init__(self, workers: int, opts: dict) -> None:
        self._opts = opts
        self._closed = False
        self._pool = _CTX.Pool(workers, initializer=_process_init, initargs=(opts,))

    def run(self, sources: list[str]) -> list[Diagram]:
        return self._pool.map(_process_render, [(source, self._opts) for source in sources])

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pool.terminate()
        self._pool.join()


# -- the public class ------------------------------------------------------------------------------


class Renderer:
    """Workers that render diagrams in parallel, started now and stopped by ``close()`` or the end of a ``with`` block.

    Args:
        workers: How many (default: the number of CPUs).
        executor: ``"thread"`` (default) or ``"process"``; see the module's docstring for which to use.
        **opts:  Options forwarded to Diagram() for every source (backend, engine, theme, config, css).

    Raises:
        ValueError, ImportError: at once, if no diagram could be rendered with these options (an unknown backend, a
            v8 engine that is not installed), before any worker is left running.

    Example::

        with mermaidx.Renderer(workers=4, backend="js:pele") as renderer:
            for batch in batches:
                for d, name in zip(renderer.render_many(batch), names):
                    d.save(name)
    """

    def __init__(self, workers: int | None = None, *, executor: str = "thread", **opts) -> None:
        if executor not in EXECUTORS:
            message = f"Unknown executor {executor!r}; expected one of {EXECUTORS}."
            raise ValueError(message)
        if workers is None:
            workers = os.cpu_count() or 1
        if workers < 1:
            message = f"workers must be at least 1, not {workers}."
            raise ValueError(message)
        Diagram(_WARM_SOURCE, **opts)  # raises for options no diagram takes, before anything is started
        self._workers = workers
        self._executor = executor
        self._closed = False
        self._backend = (_Threads if executor == "thread" else _Processes)(workers, opts)
        # Calling it stops the workers, once; it is also what runs if the Renderer is dropped without close().
        self._finalizer = weakref.finalize(self, self._backend.close)

    @property
    def workers(self) -> int:
        return self._workers

    @property
    def executor(self) -> str:
        return self._executor

    @property
    def closed(self) -> bool:
        return self._closed

    def render(self, source: str) -> Diagram:
        """Renders one diagram in a worker. A diagram that failed to render is returned unrendered, and raises on
        ``.svg()``."""
        return self.render_many([source])[0]

    def render_many(self, sources: Iterable[str]) -> list[Diagram]:
        """Renders the diagrams in parallel and returns them in the same order. Each one's SVG is already rendered, so
        ``.svg()`` returns at once; the other formats (``.png()``, ``.pdf()``, ...) are made from that SVG when first
        asked for. A diagram that failed to render is returned unrendered, and raises on ``.svg()``."""
        if self._closed:
            message = "this Renderer is closed"
            raise RuntimeError(message)
        sources = list(sources)
        if not sources:
            return []
        return self._backend.run(sources)

    def close(self) -> None:
        """Stops the workers (after the diagrams they were given) and closes their engines. Does nothing the second
        time. Call it when no ``render()`` / ``render_many()`` is running."""
        self._closed = True
        self._finalizer()

    def __enter__(self) -> Renderer:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._closed else "running"
        return f"<Renderer {self._executor} x{self._workers} {state}>"
