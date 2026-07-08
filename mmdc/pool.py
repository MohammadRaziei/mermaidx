"""
mmdc.pool — parallel batch rendering.

Rendering a Mermaid diagram is pure CPU-bound work (parsing + layout inside
QuickJS): no I/O, nothing to wait on. That rules out asyncio/threads as a
source of real concurrency here — a QuickJS context is pinned to a single
thread anyway (see engine.py), and Python's GIL means extra threads wouldn't
overlap CPU work even if it weren't. The only way to actually use more than
one CPU core is more than one process.

render_many() does exactly that: a process pool where each worker starts
its own persistent Engine once (loading mermaid.js is the expensive part)
and reuses it for every diagram routed to that worker.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from typing import Optional

from .diagram import Diagram

# 'spawn' avoids inheriting any native (QuickJS/resvg) state across fork();
# each worker starts completely fresh. Costs a bit more per-worker startup
# time, which is amortized across every diagram that worker renders.
_CTX = mp.get_context("spawn")


def _render_one(args: tuple) -> Diagram:
    source, opts = args
    return Diagram(source, **opts)


def render_many(
    sources: list,
    *,
    workers: Optional[int] = None,
    **opts,
) -> list:
    """
    Render many diagrams in parallel using a process pool.

    Args:
        sources: List of Mermaid source strings.
        workers: Number of worker processes (default: min(len(sources), cpu_count())).
        **opts:  Options forwarded to Diagram() for every source (theme, config, css).

    Returns:
        A list of Diagram objects, one per source, in the same order.

    Example::

        diagrams = mmdc.render_many([src1, src2, src3], theme="dark")
        for d, name in zip(diagrams, ["a.svg", "b.svg", "c.svg"]):
            d.save(name)
    """
    if not sources:
        return []

    if workers is None:
        workers = min(len(sources), os.cpu_count() or 1)
    workers = max(1, workers)

    if workers == 1:
        return [Diagram(s, **opts) for s in sources]

    with _CTX.Pool(workers) as pool:
        return pool.map(_render_one, [(s, opts) for s in sources])
