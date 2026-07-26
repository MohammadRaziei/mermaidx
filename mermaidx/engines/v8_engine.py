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

Why this runs in a subprocess, not a thread
---------------------------------------------
quickjs_engine.py bounds runaway diagrams (mindmap/cytoscape's internal
requestAnimationFrame-driven loop, built for a long-lived interactive page,
meaningless for a one-shot headless render) via a capped, step-by-step
job-pump loop. py_mini_racer exposes no equivalent manual microtask-pumping
control -- it drains microtasks automatically inside a single eval() call --
so a diagram type whose JS never naturally stops scheduling work has no
safety valve here and can run past `render_timeout_ms`.

An earlier version of this file ran V8 on a dedicated *thread* and, on
timeout, simply abandoned that thread (Python can't forcibly kill a
thread) and started a fresh one. That "worked" in the sense that
subsequent renders succeeded, but it permanently leaked the abandoned
thread's whole V8 isolate -- measured at ~140-160MB *every single time* --
since nothing was ever able to reclaim it. Testing confirmed
`set_hard_memory_limit()` doesn't help here either: mindmap's actual
animation loop is CPU-bound (it just keeps rescheduling itself), not one
that grows memory, so it never hits any heap ceiling to terminate it early.

A *process* doesn't have this problem: the OS can force-terminate one
unconditionally (`SIGKILL`, which cannot be blocked or ignored) and is
guaranteed to reclaim 100% of its memory immediately, no matter what state
it was stuck in. So the V8 isolate lives in a child process instead of a
thread; on timeout, that child is killed outright (not asked to stop) and
a fresh one is spawned for the next render. A killed render still raises
in the caller, exactly as before, but nothing is leaked afterward.

The child is started via the `spawn` method (a fresh interpreter), not
`fork` -- V8 is documented as unsafe to fork after initialization, and
forking a process that has other live threads (e.g. another Engine's own
child-management thread) is a general, separate correctness hazard on top
of that. `spawn` avoids both.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

from mermaidx.engines._svg_patches import patch_mindmap_centering
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

_MP_CONTEXT = mp.get_context("spawn")


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


def _build_context():
    """Boots one V8 isolate with mermaid.js loaded and ready to render.
    Only ever called *inside* the child process (see _child_main)."""
    from py_mini_racer import MiniRacer

    ctx = MiniRacer()
    ctx.eval("globalThis.__log = (s) => {};")
    ctx.eval(_measure_text_js())
    # Path bbox is pure geometry -- no Python callback needed at all,
    # identical source to quickjs_engine.py.
    ctx.eval(PATH_BBOX_JS)

    with open(_DOM_SHIM_JS, encoding="utf-8") as f:
        ctx.eval(f.read())
    with open(_MERMAID_JS, encoding="utf-8") as f:
        ctx.eval(f.read())
    ctx.eval(
        "globalThis.mermaid = (globalThis.__esbuild_esm_mermaid_nm.mermaid.default"
        " || globalThis.__esbuild_esm_mermaid_nm.mermaid);"
    )
    return ctx


def _render_svg_sync(ctx, render_count: int, code: str, theme: str,
                      config: Optional[dict], css: Optional[str]) -> str:
    render_id = f"gd{render_count}"

    base_config = {"startOnLoad": False, "theme": theme or "default",
                    "flowchart": {"htmlLabels": False}, "htmlLabels": False}
    if config:
        base_config.update(config)

    ctx.eval('if (typeof __resetDocument === "function") { __resetDocument(); }')
    ctx.eval(f"mermaid.initialize({json.dumps(base_config)});")

    if css:
        ctx.eval(f"globalThis.__css = {json.dumps(css)};")
        ctx.eval(
            "(function(){"
            "  var el = document.getElementById('mermaidx-css') || document.createElement('style');"
            "  el.setAttribute('id', 'mermaidx-css');"
            "  el.textContent = __css;"
            "  document.head.appendChild(el);"
            "})();"
        )

    ctx.eval("globalThis.__renderResult = null; globalThis.__renderError = null;")
    ctx.eval(
        f"""
mermaid.render({json.dumps(render_id)}, {json.dumps(code)})
  .then(r => {{ globalThis.__renderResult = r.svg; }})
  .catch(e => {{ globalThis.__renderError = (e && e.name ? e.name + ": " + e.message : String(e)); }});
"""
    )

    err = ctx.eval("globalThis.__renderError")
    if err:
        raise MermaidRenderError(str(err))
    svg = ctx.eval("globalThis.__renderResult")
    if not svg:
        raise MermaidRenderError("mermaid.render() produced no output (unknown error)")
    return patch_mindmap_centering(str(svg))


def _child_main(conn) -> None:
    """
    Entry point of the child process (see Engine -- one child == one V8
    isolate). Boots V8 once, then serves render requests from the parent
    over `conn` until told to stop or the pipe closes. Never returns
    normally except on shutdown -- if this hangs, the parent's only
    recourse is killing the process outright (see module docstring), which
    is exactly the point: nothing in here needs to handle that gracefully.
    """
    try:
        ctx = _build_context()
        conn.send(("ready", None))
    except Exception as exc:  # noqa: BLE001 -- report *any* boot failure to the parent
        conn.send(("boot_error", f"{type(exc).__name__}: {exc}"))
        return

    render_count = 0
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return  # parent went away
        if msg is None:  # shutdown sentinel
            return

        render_count += 1
        code, theme, config, css = msg
        try:
            svg = _render_svg_sync(ctx, render_count, code, theme, config, css)
            conn.send(("ok", svg))
        except MermaidRenderError as exc:
            conn.send(("render_error", str(exc)))
        except Exception as exc:  # noqa: BLE001 -- report *any* other failure to the parent
            conn.send(("render_error", f"{type(exc).__name__}: {exc}"))


class Engine:
    """
    One Engine = one child process with a V8 isolate + mermaid.js loaded
    (see module docstring for why a process, not a thread). Same
    start()/close()/started/render_svg() surface as
    quickjs_engine.Engine -- diagram.py doesn't need to know which one it
    has.
    """

    def __init__(self, render_timeout_ms: int = _DEFAULT_RENDER_TIMEOUT_MS) -> None:
        self._process: Optional[mp.process.BaseProcess] = None
        self._parent_conn = None
        self._render_timeout_ms = render_timeout_ms
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._process is not None:
            return
        self._spawn()

    def _spawn(self) -> None:
        parent_conn, child_conn = _MP_CONTEXT.Pipe()
        process = _MP_CONTEXT.Process(target=_child_main, args=(child_conn,), daemon=True)
        process.start()
        child_conn.close()  # only the child needs its end

        # Booting -- loading mermaid.js -- can itself take a moment; give it
        # the same generous timeout as a render, rather than a separate one.
        if not parent_conn.poll(timeout=self._render_timeout_ms / 1000):
            process.kill()
            raise MermaidRenderError(
                f"V8 engine failed to boot within {self._render_timeout_ms}ms."
            )
        status, payload = parent_conn.recv()
        if status != "ready":
            process.kill()
            raise MermaidRenderError(f"V8 engine failed to boot: {payload}")

        self._process = process
        self._parent_conn = parent_conn

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            conn, self._parent_conn = self._parent_conn, None
        if process is None:
            return
        try:
            if conn is not None:
                conn.send(None)  # ask nicely first
            process.join(timeout=2)
        except Exception:  # noqa: BLE001 -- best-effort; kill below covers any failure
            pass
        if process.is_alive():
            process.kill()  # SIGKILL -- guaranteed, immediate, no leak
            process.join(timeout=2)
        if conn is not None:
            conn.close()

    @property
    def started(self) -> bool:
        return self._process is not None

    # -- public, thread-safe entry point ---------------------------------------

    def render_svg(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        """
        Sends the render to the child process and waits for a reply, with
        a timeout. A diagram whose JS never stops scheduling work (e.g.
        mindmap -- see module docstring) means no reply ever comes; when
        that happens, the child is killed outright (SIGKILL -- the OS
        reclaims all of its memory immediately, unconditionally) and a
        fresh one is spawned for the next call. The current call still
        raises, but nothing is left behind afterward -- unlike the
        thread-based approach this replaced, which had to choose between
        hanging forever or leaking the isolate permanently.
        """
        with self._lock:
            process, conn = self._process, self._parent_conn
        if process is None or conn is None:
            raise RuntimeError("Engine is not started.")

        conn.send((code, theme, config, css))
        if not conn.poll(timeout=self._render_timeout_ms / 1000):
            with self._lock:
                if self._process is process:  # don't clobber a respawn done by another thread
                    self._process = None
                    self._parent_conn = None
            process.kill()  # SIGKILL: guaranteed to free 100% of this process's memory
            process.join(timeout=2)
            conn.close()
            self.start()  # fresh child for subsequent calls
            raise MermaidRenderError(
                f"Render exceeded {self._render_timeout_ms}ms and was killed "
                "(this diagram's JS never stopped scheduling work -- see "
                "engines/v8_engine.py's module docstring for why). A fresh V8 "
                "engine has been started for subsequent renders; no memory was "
                "leaked by this one. Use backend=\"quickjs\" for this diagram."
            )

        try:
            status, payload = conn.recv()
        except (EOFError, OSError) as exc:
            # The child died on its own (e.g. crashed) rather than just
            # hanging -- same recovery as the timeout case above.
            with self._lock:
                if self._process is process:
                    self._process = None
                    self._parent_conn = None
            process.join(timeout=2)
            conn.close()
            self.start()
            raise MermaidRenderError("The V8 engine process died unexpectedly.") from exc

        if status == "ok":
            return payload
        raise MermaidRenderError(payload)
