"""
mermaidx.pool -- ``render_many()``, the one-call form of mermaidx.renderer.Renderer.

``render_many(sources)`` starts the workers, renders, and stops them before it returns; nothing is kept between calls.
To render several batches, make a Renderer once and call its ``render_many()`` for each: starting workers loads an
engine in each of them (about 0.1 s each with the bytecode cache, a second or more without it, and for processes
a fresh interpreter on top), which a small batch spends more time on than on drawing.

See mermaidx.renderer for why the workers are threads by default, and for ``executor="process"``.
"""

from __future__ import annotations

import os
from typing import Iterable

from .diagram import Diagram
from .renderer import Renderer, _render_one


def render_many(
    sources: Iterable[str],
    *,
    workers: int | None = None,
    executor: str = "thread",
    **opts,
) -> list[Diagram]:
    """
    Render many diagrams in parallel.

    Args:
        sources: Mermaid source strings.
        workers: Number of workers (default: min(len(sources), cpu_count()); never more than there are sources).
        executor: ``"thread"`` (default) or ``"process"``; see ``mermaidx.Renderer``.
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

    To render more than one batch, keep the workers between them with ``mermaidx.Renderer``.
    """
    sources = list(sources)
    if not sources:
        return []

    if workers is None:
        workers = min(len(sources), os.cpu_count() or 1)
    workers = max(1, min(workers, len(sources)))

    if workers == 1:
        return [_render_one(source, opts) for source in sources]

    with Renderer(workers, executor=executor, **opts) as renderer:
        return renderer.render_many(sources)
