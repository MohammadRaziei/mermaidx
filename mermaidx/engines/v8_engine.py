"""
mermaidx.engines.v8_engine -- mermaid.js running inside real V8 (via the
`mini-racer` package, imported as `py_mini_racer`) instead of QuickJS-ng.

Same public shape as mermaidx.engines.quickjs_engine on purpose: class name
`Engine`, exception `MermaidRenderError`, and the same
start()/close()/started/render_svg() surface. Switching mermaidx.diagram
between engines is a single import-line change:

    from mermaidx.engines.quickjs_engine import Engine, MermaidRenderError
    # vs.
    from mermaidx.engines.v8_engine import Engine, MermaidRenderError

Why this exists: V8 has a JIT, QuickJS-ng doesn't, so the same real
mermaid.js + dagre layout work runs noticeably faster here (see
benchmark scripts) -- at the cost of a real, documented limitation below.

Why text measurement works differently here
---------------------------------------------
QuickJS lets Python expose a *synchronous* callable straight into JS
(`ctx.add_callable`), so mermaid.js's synchronous `getBBox()`/
`getComputedTextLength()` calls can call straight back into Python for
every single measurement, mid-layout, without anything special.

`py_mini_racer`'s only supported callback mechanism is *async* Python
functions (V8 disallows re-entrant synchronous callbacks into an
embedder for safety/deadlock reasons) -- but mermaid.js calls these DOM
methods synchronously and can't be made to `await` them without editing
mermaid.js itself, which this project deliberately never does.

The fix used here isn't a callback at all: mermaidx.font_metrics.measure()
does nothing but sum per-character advance widths (no kerning, no
ligatures -- see that module's docstring), so instead of measuring text
live, this engine ships the *entire* per-codepoint advance-width table for
both the regular and bold bundled fonts into V8 once at boot
(Font.full_advance_table()), and JS sums it locally. This is not an
approximation -- it reproduces mermaidx.font_metrics.Font.measure() exactly
(same tables, same formula), just computed in JS instead of Python. Any
codepoint outside the table (extremely unlikely -- DejaVu Sans covers
Latin/Greek/Cyrillic/general punctuation/symbols) falls back to the
font's own notdef-glyph width, exactly like the Python path does.

Known limitation (unlike quickjs_engine.py)
---------------------------------------------
quickjs_engine.py bounds runaway diagrams (mindmap/cytoscape's internal
requestAnimationFrame-driven loop, built for a long-lived interactive page)
via a capped, step-by-step job-pump loop. py_mini_racer exposes no
equivalent manual microtask-pumping control -- it drains microtasks
automatically inside a single eval() call -- so a diagram type whose JS
never naturally stops scheduling work has no safety valve here and could
block past `render_timeout_ms`. All diagram types tested for this project
(flowchart/sequence/gantt/erDiagram/classDiagram) do not do this; mindmap
is the one known type from mermaidx's own architecture notes that might.
"""

from __future__ import annotations

import json
import queue
import re
import threading
from concurrent.futures import Future
from functools import lru_cache
from pathlib import Path
from typing import Optional

from py_mini_racer import MiniRacer
from py_mini_racer._exc import MiniRacerBaseException

from mermaidx.font_metrics import get_font
from mermaidx.path_bbox import PATH_BBOX_JS

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_DOM_SHIM_JS = _ASSETS_DIR / "dom_shim.js"
_MERMAID_JS = _ASSETS_DIR / "mermaid.js"

_DEFAULT_RENDER_TIMEOUT_MS = 8_000
# Real renders finish in well under a second even for fairly large diagrams
# (see the benchmark scripts) -- this default is generous headroom for that,
# not a "how slow can a real diagram legitimately be" estimate. It exists
# almost entirely as the bound on the one known failure mode (see
# Engine.render_svg's docstring): a diagram type whose JS never stops
# scheduling itself. Lower is better there, since there's nothing to wait
# for; raise it only if you have genuinely huge/slow diagrams timing out.


class MermaidRenderError(RuntimeError):
    """Raised when mermaid.js itself reports a parse/render error."""


@lru_cache(maxsize=None)
def _measure_text_js() -> str:
    """Builds the one-time JS source that reproduces
    mermaidx.font_metrics.Font.measure() exactly, using the same bundled
    fonts' full per-codepoint advance tables -- see module docstring."""
    regular = get_font(None)
    bold = get_font("bold")

    payload = {
        "regular": {
            "advances": regular.full_advance_table(),
            "notdef": regular.notdef_advance_units(),
            **regular.metrics_summary(),
        },
        "bold": {
            "advances": bold.full_advance_table(),
            "notdef": bold.notdef_advance_units(),
            **bold.metrics_summary(),
        },
    }

    return f"""
(function () {{
  const FONTS = {json.dumps(payload)};

  function pickFont(weight) {{
    const w = String(weight == null ? "" : weight).trim().toLowerCase();
    const n = Number(weight);
    if ((!Number.isNaN(n) && n >= 600) || w === "bold" || w === "bolder") {{
      return FONTS.bold;
    }}
    return FONTS.regular;
  }}

  function measureFull(text, size, family, weight, style) {{
    const font = pickFont(weight);
    const s = text == null ? "" : String(text);
    let totalUnits = 0;
    for (const ch of s) {{
      const cp = ch.codePointAt(0);
      const adv = font.advances[cp];
      totalUnits += adv === undefined ? font.notdef : adv;
    }}
    const sizePx = Number(size) || 16;
    const scale = sizePx / font.unitsPerEm;
    return {{
      width: totalUnits * scale,
      ascent: font.ascender * scale,
      descent: -font.descender * scale,
    }};
  }}

  globalThis.__measureTextFull = measureFull;
  globalThis.__measureText = (t, s, f, w, st) => measureFull(t, s, f, w, st).width;
}})();
"""


class _DaemonSingleThreadExecutor:
    """
    A single-worker executor, like `ThreadPoolExecutor(max_workers=1)`, but
    using a *daemon* thread. Regular ThreadPoolExecutor threads are joined
    at interpreter exit no matter what (via an atexit hook registered deep
    in `concurrent.futures.thread`) -- fine normally, but Engine.render_svg
    deliberately abandons a wedged worker thread rather than waiting on it
    forever (see its docstring for why), and a leaked non-daemon thread
    would then block the whole process from exiting even after the Engine
    itself has already recovered. A daemon thread is killed by the OS
    process teardown instead, so an abandoned one no longer matters.
    """

    def __init__(self, thread_name: str) -> None:
        self._queue: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._worker, name=thread_name, daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:  # shutdown sentinel
                return
            fn, args, future = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(*args))
            except BaseException as exc:  # noqa: BLE001 -- propagate anything to the caller
                future.set_exception(exc)

    def submit(self, fn, *args) -> Future:
        future: Future = Future()
        self._queue.put((fn, args, future))
        return future

    def shutdown(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)  # a wedged worker won't join -- that's fine, it's a daemon


class Engine:
    """
    One Engine = one V8 isolate with mermaid.js loaded, pinned to one
    dedicated worker thread (mirrors quickjs_engine.Engine's shape/lifecycle
    exactly, so mermaidx.diagram doesn't need to know which one it has).
    """

    def __init__(self, render_timeout_ms: int = _DEFAULT_RENDER_TIMEOUT_MS) -> None:
        self._executor: Optional[_DaemonSingleThreadExecutor] = None
        self._ctx: Optional[MiniRacer] = None
        self._render_count = 0
        self._render_timeout_ms = render_timeout_ms
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._executor is not None:
            return
        self._executor = _DaemonSingleThreadExecutor(thread_name="mermaidx-v8-engine")
        self._executor.submit(self._init_context).result()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None
            self._ctx = None

    @property
    def started(self) -> bool:
        return self._executor is not None

    # -- worker-thread-only methods ---------------------------------------

    def _init_context(self) -> None:
        ctx = MiniRacer()
        ctx.eval("globalThis.__log = (s) => {};")
        ctx.eval(_measure_text_js())
        # Path bbox is pure geometry -- no Python callback needed at all,
        # identical source to quickjs_engine.py.
        ctx.eval(PATH_BBOX_JS)

        with open(_DOM_SHIM_JS, encoding="utf-8") as f:
            ctx.eval(f.read(), timeout=self._render_timeout_ms)
        with open(_MERMAID_JS, encoding="utf-8") as f:
            ctx.eval(f.read(), timeout=self._render_timeout_ms)
        ctx.eval(
            "globalThis.mermaid = (globalThis.__esbuild_esm_mermaid_nm.mermaid.default"
            " || globalThis.__esbuild_esm_mermaid_nm.mermaid);"
        )
        self._ctx = ctx

    def _render_svg_sync(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        assert self._ctx is not None
        ctx = self._ctx
        self._render_count += 1
        render_id = f"gd{self._render_count}"

        base_config = {"startOnLoad": False, "theme": theme or "default",
                        "flowchart": {"htmlLabels": False}, "htmlLabels": False}
        if config:
            base_config.update(config)

        ctx.eval('if (typeof __resetDocument === "function") { __resetDocument(); }',
                  timeout=self._render_timeout_ms)
        ctx.eval(f"mermaid.initialize({json.dumps(base_config)});", timeout=self._render_timeout_ms)

        if css:
            ctx.eval(f"globalThis.__css = {json.dumps(css)};")
            ctx.eval(
                "(function(){"
                "  var el = document.getElementById('mermaidx-css') || document.createElement('style');"
                "  el.setAttribute('id', 'mermaidx-css');"
                "  el.textContent = __css;"
                "  document.head.appendChild(el);"
                "})();",
                timeout=self._render_timeout_ms,
            )

        ctx.eval("globalThis.__renderResult = null; globalThis.__renderError = null;")
        try:
            ctx.eval(
                f"""
mermaid.render({json.dumps(render_id)}, {json.dumps(code)})
  .then(r => {{ globalThis.__renderResult = r.svg; }})
  .catch(e => {{ globalThis.__renderError = (e && e.name ? e.name + ": " + e.message : String(e)); }});
""",
                timeout=self._render_timeout_ms,
            )
        except MiniRacerBaseException as exc:
            raise MermaidRenderError(f"V8 execution error: {exc}") from exc

        err = ctx.eval("globalThis.__renderError")
        if err:
            raise MermaidRenderError(str(err))
        svg = ctx.eval("globalThis.__renderResult")
        if not svg:
            raise MermaidRenderError("mermaid.render() produced no output (unknown error)")
        svg = str(svg)
        # Same mindmap centering patch as quickjs_engine.py -- see there for
        # why this is needed (mermaid's own dead CSS rule for this class).
        if "<style" in svg and "section-root" in svg:
            svg = re.sub(
                r"(<style[^>]*>)",
                r"\1.section-root .label text{text-anchor:middle;}",
                svg,
                count=1,
            )
        return svg

    # -- public, thread-safe entry point ---------------------------------------

    def render_svg(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        """
        Submits the render to the dedicated worker thread and waits for it,
        with a Python-level timeout as a safety net independent of
        py_mini_racer's own per-eval `timeout=` (see the "Known limitation"
        note in this module's docstring: a diagram whose JS never stops
        scheduling work -- e.g. mindmap -- can run past that per-eval
        timeout since it keeps rescheduling itself rather than blocking in
        one eval() call).

        Python cannot forcibly kill a running thread, so a timed-out call
        leaves one worker thread permanently stuck inside V8. Rather than
        letting that wedge every future render through this same Engine
        (max_workers=1 means everything else would simply queue forever
        behind it), this discards the stuck executor and starts a fresh one
        for subsequent calls -- the current call still raises, but the
        Engine heals itself instead of becoming permanently unusable.
        """
        with self._lock:
            executor = self._executor
        if executor is None:
            raise RuntimeError("Engine is not started.")

        future = executor.submit(self._render_svg_sync, code, theme, config, css)
        try:
            return future.result(timeout=self._render_timeout_ms / 1000)
        except TimeoutError as exc:
            with self._lock:
                if self._executor is executor:  # don't clobber a healing done by another thread
                    self._executor = None
                    self._ctx = None
            self.start()  # fresh executor + context for subsequent calls
            raise MermaidRenderError(
                f"Render exceeded {self._render_timeout_ms}ms and was abandoned "
                "(the underlying V8 worker thread cannot be interrupted, so a new "
                "engine instance was started for subsequent renders)."
            ) from exc
