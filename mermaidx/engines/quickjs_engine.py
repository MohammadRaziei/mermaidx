"""
mermaidx.engines.quickjs_engine — mermaid.js running inside QuickJS-ng.

Same public shape as mermaidx.engines.v8_engine on purpose: class name
`Engine`, exception `MermaidRenderError`, and the same
start()/close()/started/render_svg() surface. Switching mermaidx.diagram
between engines is a single import-line change:

    from mermaidx.engines.quickjs_engine import Engine, MermaidRenderError
    # vs.
    from mermaidx.engines.v8_engine import Engine, MermaidRenderError

Since QuickJS has no DOM, a minimal fake DOM/SVG implementation is loaded
first (assets/dom_shim.js). Text metrics (`getBBox` / `getComputedTextLength`)
are bridged back into Python, where mermaidx.font_metrics reads real glyph
advance widths from a bundled font file (DejaVu Sans) -- the same font file
mermaidx.raster (novasvg) is told to use for final rendering, so layout and
paint always agree.
Path bounding boxes (mermaidx.path_bbox) are pure geometry with no Python
dependency, so they run entirely inside the JS engine -- no callback needed.

A dedicated single-thread executor owns the QuickJS context, since QuickJS
contexts are not thread-safe and must always be driven from one thread.
"""

from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import quickjs

from mermaidx.engines._common import MermaidRenderError, TextMeasurer, collect_svg, context_scripts, render_script, run_event_loop  # noqa: F401 (re-exported: the engines are interchangeable by their import line)


# A browser gives a page's JS a stack deep enough for mermaid.js's recursion (dagre walks a long chain of
# nodes depth-first; QuickJS's default limit, 256 KiB, runs out at ~100 chained nodes). The worker thread's own
# native stack is sized explicitly, and the JS limit sits below it, so hitting the limit is always a JS
# RangeError and never a segfault -- whatever the platform's default thread stack is (512 KiB on macOS).
_WORKER_THREAD_STACK_BYTES = 32 * 1024 * 1024
_JS_STACK_LIMIT_BYTES = 24 * 1024 * 1024


class Engine:
    """
    One Engine = one QuickJS context with mermaid.js loaded, pinned to one
    dedicated worker thread. Reused across many renders (loading mermaid.js
    itself, ~6MB of source, is the expensive part -- do it once).
    """

    def __init__(self) -> None:
        self._executor: Optional[ThreadPoolExecutor] = None
        self._ctx: Optional[quickjs.Context] = None
        self._measurer: Optional[TextMeasurer] = None
        self._render_count = 0
        self._ctx_used = False
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._executor is not None:
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mermaidx-engine")
        # The executor starts its thread inside the first submit(); threading.stack_size() is process-wide,
        # so it is set only around that call and put back right after.
        previous = threading.stack_size(_WORKER_THREAD_STACK_BYTES)
        try:
            first = self._executor.submit(self._init_context)
        finally:
            threading.stack_size(previous)
        first.result()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
            self._ctx = None
            self._measurer = None

    @property
    def started(self) -> bool:
        return self._executor is not None

    # -- worker-thread-only methods ---------------------------------------

    def _init_context(self) -> None:
        self._measurer = TextMeasurer()
        self._ctx = self._build_context()
        self._ctx_used = False

    def _ensure_fresh_context(self) -> None:
        """Make sure self._ctx has not rendered anything yet.

        mermaid.js keeps module-level state (id counters such as the sequence diagram's actor1/actor2...,
        the class diagram's classId-N-M) that a browser starts from zero on every page load; mermaid-cli
        opens a new page for each diagram. A context that already rendered would number the next
        diagram's ids on from where the last one stopped, so each render gets a context of its own."""
        if self._ctx is None or self._ctx_used:
            self._ctx = self._build_context()
            self._ctx_used = False

    def _build_context(self):
        ctx = quickjs.Context()
        ctx.set_memory_limit(512 * 1024 * 1024)
        ctx.set_max_stack_size(_JS_STACK_LIMIT_BYTES)
        # NOTE: no ctx.set_time_limit() -- quickjs forbids calling back into
        # Python (needed constantly for text measurement) while a time limit
        # is active. Runaway scripts are bounded instead by the job-pump cap.

        ctx.add_callable("__log_raw", lambda s: print(f"[mermaidx/js] {s}", file=sys.stderr))
        ctx.add_callable(
            "__measureText_raw",
            lambda t, s, f, w, st: self._measurer.width(t, s, f, w, st),
        )
        ctx.add_callable(
            "__measureTextFull_raw",
            lambda t, s, f, w, st: json.dumps(self._measurer.full(t, s, f, w, st)),
        )
        ctx.add_callable(
            "__measureGlyphs_raw",
            lambda t, s, f, w, st: json.dumps(self._measurer.glyphs(t, s, f, w, st)),
        )
        ctx.add_callable(
            "__measureForeignObject_raw",
            lambda h, s, f, w, st: json.dumps(self._measurer.foreign_object(h, s, f, w, st)),
        )

        ctx.eval(
            "globalThis.__log = (s) => __log_raw(s);\n"
            "globalThis.__measureText = (t,s,f,w,st) => __measureText_raw(t,s,f,w,st);\n"
            "globalThis.__measureTextFull = (t,s,f,w,st) => JSON.parse(__measureTextFull_raw(t,s,f,w,st));\n"
            "globalThis.__measureGlyphs = (t,s,f,w,st) => JSON.parse(__measureGlyphs_raw(t,s,f,w,st));\n"
            "globalThis.__measureForeignObject = (h,s,f,w,st) => JSON.parse(__measureForeignObject_raw(h,s,f,w,st));\n"
        )
        for script in context_scripts():
            ctx.eval(script)
        return ctx

    def _run_job(self) -> bool:
        """Runs one pending promise job; False when there is none."""
        try:
            return bool(self._ctx.execute_pending_job())
        except StopIteration:
            return False

    def _render_svg_sync(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        self._ensure_fresh_context()
        ctx = self._ctx
        self._ctx_used = True
        self._render_count += 1
        ctx.eval(render_script(code, theme, config, css))
        run_event_loop(ctx.eval, self._run_job)

        return collect_svg(ctx.eval)

    # -- public, thread-safe entry point ---------------------------------------

    def render_svg(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        if self._executor is None:
            raise RuntimeError("Engine is not started.")
        result = self._executor.submit(self._render_svg_sync, code, theme, config, css).result()
        # Build the next render's context now, off the caller's path, while it is likely idle.
        self._executor.submit(self._ensure_fresh_context)
        return result
