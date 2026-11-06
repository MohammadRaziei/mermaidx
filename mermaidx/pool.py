"""
mermaidx.pool — parallel batch rendering.

Rendering a Mermaid diagram is pure CPU-bound work (parsing + layout inside
a JS engine): no I/O, nothing to wait on. That rules out asyncio/threads as a
source of real concurrency here — a QuickJS context is pinned to a single
thread anyway (see engines/quickjs_engine.py), and Python's GIL means extra
threads wouldn't overlap CPU work even if it weren't. The only way to actually
use more than one CPU core is more than one process.

render_many() does exactly that: a process pool where each worker starts
its own persistent Engine once (loading mermaid.js is the expensive part)
and reuses it for every diagram routed to that worker. The worker renders the
SVG -- the expensive part -- before it sends the Diagram back, so the work
really happens in the workers: a Diagram is lazy, and one returned
unrendered would be rendered later, one after another, in the caller's process
(https://github.com/MohammadRaziei/mermaidx/issues/43).

The pool outlives the call. Starting a worker (a fresh interpreter, the imports, the engine with its JS library) costs
0.2 s for js:pele and about a second for js:mermaid, and a batch of a few diagrams spends more on that than on
rendering them, so the next render_many() with the same number of workers is handed the workers the last one left
running, engines warm. They stop when the interpreter exits, or at once with shutdown_pool(); render_many(...,
reuse_pool=False) uses a pool of its own and stops it before it returns.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
import os
import threading
from typing import Optional

from .diagram import Diagram

# 'spawn' avoids inheriting any native (QuickJS/novasvg) state across fork();
# each worker starts completely fresh. Costs a bit more per-worker startup
# time, which is amortized across every diagram that worker renders.
_CTX = mp.get_context("spawn")


def _render_one(args: tuple) -> Diagram:
    source, opts = args
    d = Diagram(source, **opts)
    try:
        d.svg()  # parse + layout, in this process; the SVG is cached in `d` and travels back with it
    except Exception:
        # Leave it uncached: the error then surfaces on the caller's own .svg(), as it did when render_many()
        # was lazy, and one bad diagram does not take the whole batch down.
        pass
    return d


class _SharedPool:
    """The pool render_many() leaves running between calls, and how many calls are using it right now."""

    __slots__ = ("in_flight", "pid", "pool", "workers")

    def __init__(self, workers: int) -> None:
        self.pool = _CTX.Pool(workers)
        self.workers = workers
        self.pid = os.getpid()
        self.in_flight = 0


_lock = threading.Lock()
_shared: _SharedPool | None = None
_atexit_registered = False


def _stop(shared: _SharedPool) -> None:
    """Stops the workers of a pool that is ours (a process that inherited it by fork must leave it to its parent)."""
    if shared.pid == os.getpid():
        shared.pool.terminate()
        shared.pool.join()


def _checkout(workers: int) -> _SharedPool | None:
    """The shared pool of `workers` workers, started if there is none, marked as in use. None when it cannot be had:
    another call is using a pool of another size, which must not be stopped under it (the caller then makes a pool
    of its own for this one call)."""
    global _shared, _atexit_registered  # noqa: PLW0603
    with _lock:
        shared = _shared
        if shared is not None and shared.pid != os.getpid():
            shared = _shared = None  # inherited through fork(): its workers belong to the parent
        if shared is not None and shared.workers != workers:
            if shared.in_flight:
                return None
            _stop(shared)
            shared = _shared = None
        if shared is None:
            shared = _shared = _SharedPool(workers)
            if not _atexit_registered:
                atexit.register(shutdown_pool)
                _atexit_registered = True
        shared.in_flight += 1
        return shared


def _release(shared: _SharedPool) -> None:
    with _lock:
        shared.in_flight -= 1


def _discard(shared: _SharedPool) -> None:
    """A call that ended with an error (or an interrupt) may leave tasks running in the workers: stop them, so the
    next call does not queue behind work nobody wants."""
    global _shared  # noqa: PLW0603
    with _lock:
        if _shared is shared:
            _shared = None
    _stop(shared)


def shutdown_pool() -> None:
    """Stops the worker processes render_many() keeps running between calls (it does so by itself when the
    interpreter exits). The next render_many() starts new ones. Call it when no render_many() is running."""
    global _shared
    with _lock:
        shared, _shared = _shared, None
    if shared is not None:
        _stop(shared)


def render_many(
    sources: list,
    *,
    workers: Optional[int] = None,
    reuse_pool: bool = True,
    **opts,
) -> list:
    """
    Render many diagrams in parallel using a process pool.

    Args:
        sources: List of Mermaid source strings.
        workers: Number of worker processes (default: min(len(sources), cpu_count())).
        reuse_pool: Keep the worker processes running after the call, for the next ``render_many()`` with the same
            number of workers to use (default). ``False`` starts workers for this call alone and stops them
            before it returns; see also ``shutdown_pool()``.
        **opts:  Options forwarded to Diagram() for every source (backend, engine, theme, config, css).

    Returns:
        A list of Diagram objects, one per source, in the same order. Each one's SVG is already rendered (by
        the worker), so ``.svg()`` returns at once; the other formats (``.png()``, ``.pdf()``, ...) are made
        from that SVG when first asked for. A diagram that failed to render is returned unrendered, and
        raises on ``.svg()``.

    Example::

        diagrams = mermaidx.render_many([src1, src2, src3], theme="dark")
        for d, name in zip(diagrams, ["a.svg", "b.svg", "c.svg"]):
            d.save(name)
    """
    if not sources:
        return []

    if workers is None:
        workers = min(len(sources), os.cpu_count() or 1)
    workers = max(1, workers)

    if workers == 1:
        return [_render_one((s, opts)) for s in sources]

    tasks = [(s, opts) for s in sources]
    shared = _checkout(workers) if reuse_pool else None
    if shared is None:
        with _CTX.Pool(workers) as pool:
            return pool.map(_render_one, tasks)
    try:
        return shared.pool.map(_render_one, tasks)
    except BaseException:
        _discard(shared)
        raise
    finally:
        _release(shared)
