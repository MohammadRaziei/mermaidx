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

The fix used here isn't a callback at all: this engine ships the *entire*
per-codepoint advance-width table for both the regular and bold bundled
fonts into V8 once at boot (Font.full_advance_table()), plus a sparse
kerning-adjustment table for printable-ASCII codepoint pairs
(Font.ascii_kerning_pairs()), and JS sums both locally instead of
measuring text live (see measureFull() below). This reproduces
mermaidx.font_metrics.Font.measure() -- which, via novasvg's own
Font.measureText(), *does* apply real kerning between every glyph pair --
exactly for any text made up of printable ASCII characters (virtually all
real diagram labels): same per-codepoint advances, same per-pair kerning
adjustments where the font has any, same formula, just computed in JS
instead of Python. A kerning adjustment between two NON-ASCII codepoints
(rare in practice, and not something the bundled DejaVu Sans has much of
outside Latin text anyway) isn't in the shipped table and so is silently
treated as zero -- see Font.ascii_kerning_pairs()'s own docstring for why
a full, exhaustive kerning table isn't cheap to build the way the
per-codepoint advance table is. Any codepoint outside the advance table
(extremely unlikely -- DejaVu Sans covers Latin/Greek/Cyrillic/general
punctuation/symbols) falls back to the font's own notdef-glyph width,
exactly like the Python path does.

Why this runs in a subprocess, not a thread
---------------------------------------------
quickjs_engine.py bounds runaway diagrams (mindmap's and architecture's cytoscape internal
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
from typing import Optional

from mermaidx.engines._common import MermaidRenderError, TextMeasurer, collect_svg, context_scripts, render_script, run_event_loop
from mermaidx.font_metrics import get_font

_DEFAULT_RENDER_TIMEOUT_MS = 8_000
# Starting the child (spawn, imports, loading mermaid.js) is not a render and is not bounded by the render
# timeout: a caller's tight render budget must not turn a slow spawn into "failed to boot".
_BOOT_TIMEOUT_MS = 60_000
# Real renders finish in well under a second even for fairly large diagrams
# (see the benchmark scripts) -- this default is generous headroom for that,
# not a "how slow can a real diagram legitimately be" estimate. It exists
# almost entirely as the bound on the one known failure mode (see
# Engine.render_svg's docstring): a diagram type whose JS never stops
# scheduling itself. Lower is better there, since there's nothing to wait
# for; raise it only if you have genuinely huge/slow diagrams timing out.

_MP_CONTEXT = mp.get_context("spawn")


@lru_cache(maxsize=None)
def _measure_text_js() -> str:
    """Builds the one-time JS source that reproduces
    mermaidx.font_metrics.Font.measure() for printable-ASCII text (see
    module docstring for the non-ASCII-kerning caveat), using the same
    bundled fonts' full per-codepoint advance tables plus a sparse
    ASCII kerning table."""
    regular = get_font(None)
    bold = get_font("bold")

    payload = {
        "regular": {
            "advances": regular.full_advance_table(),
            "notdef": regular.notdef_advance_units(),
            "kerning": regular.ascii_kerning_pairs(),
            "ligatures": regular.ligatures(),
            "ink": regular.full_glyph_table(),
            "notdefInk": regular.notdef_glyph_box(),
            **regular.metrics_summary(),
        },
        "bold": {
            "advances": bold.full_advance_table(),
            "notdef": bold.notdef_advance_units(),
            "kerning": bold.ascii_kerning_pairs(),
            "ligatures": bold.ligatures(),
            "ink": bold.full_glyph_table(),
            "notdefInk": bold.notdef_glyph_box(),
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

  // The walk Font::measureText() and Font::glyphBoxes() make (novasvg's detail/font.h): for each codepoint,
  // an f-ligature if the font has one for the sequence starting here (longest first), then the kerning
  // between it and the glyph before it, then its advance. Returns every glyph's pen position in font units.
  function walk(text, font) {{
    const cps = Array.from(text == null ? "" : String(text), (ch) => ch.codePointAt(0));
    const glyphs = [];
    let pen = 0, prev = null;
    for (let i = 0; i < cps.length; i++) {{
      let cp = cps[i];
      const lig = font.ligatures.find(([seq]) => seq.every((c, k) => cps[i + k] === c));
      if (lig) {{ cp = lig[1]; i += lig[0].length - 1; }}
      if (prev !== null) {{
        // Only printable-ASCII pairs are in the table (see Font.ascii_kerning_pairs); any other pair is 0.
        const k = font.kerning[prev + "," + cp];
        if (k !== undefined) pen += k;
      }}
      prev = cp;
      glyphs.push({{ cp, pen }});
      const adv = font.advances[cp];
      pen += adv === undefined ? font.notdef : adv;
    }}
    return {{ glyphs, units: pen }};
  }}

  function measureFull(text, size, family, weight, style) {{
    const font = pickFont(weight);
    const scale = (Number(size) || 16) / font.unitsPerEm;
    return {{
      width: walk(text, font).units * scale,
      ascent: font.ascender * scale,
      descent: -font.descender * scale,
      xHeight: font.xHeight * scale,
    }};
  }}

  // [pen, ink_left, ink_right, ink_top, ink_bottom] in px for every glyph with an outline (a space has none).
  function measureGlyphs(text, size, family, weight, style) {{
    const font = pickFont(weight);
    const scale = (Number(size) || 16) / font.unitsPerEm;
    const boxes = [];
    for (const {{ cp, pen }} of walk(text, font).glyphs) {{
      const ink = font.ink[cp] || (font.advances[cp] === undefined ? font.notdefInk : null);
      if (ink) boxes.push([pen * scale, ink[0] * scale, ink[1] * scale, ink[2] * scale, ink[3] * scale]);
    }}
    return boxes;
  }}

  globalThis.__measureTextFull = measureFull;
  globalThis.__measureGlyphs = measureGlyphs;
  globalThis.__measureText = (t, s, f, w, st) => measureFull(t, s, f, w, st).width;

  // <foreignObject> labels are laid out by novasvg (wrapping, bold and italic runs, a declared width...): too
  // much to copy here, and V8 cannot call back into Python while it runs. So the page is rendered more than
  // once. A label whose size is not in __foKnown is recorded in __foMissing and given a rough size; the child
  // process asks novasvg for exactly the recorded ones, and the page is rendered again with them in
  // __foKnown, until nothing new is asked (see _render below).
  globalThis.__foKnown = {{}};
  globalThis.__foMissing = {{}};
  globalThis.__measureForeignObject = (html, size, family, weight, style) => {{
    const key = JSON.stringify([html, size, family, weight, style]);
    if (globalThis.__foKnown[key]) return globalThis.__foKnown[key];
    globalThis.__foMissing[key] = [html, size, family, weight, style];
    const px = Number(size) || 16;
    const m = measureFull("M", px, family, weight, style);
    const lineHeight = (m.ascent + m.descent) * 1.2;
    const text = String(html == null ? "" : html).replace(/<[^>]*>/g, " ").trim();
    return {{ width: measureFull(text, px, family, weight, style).width, height: lineHeight, line_count: 1, line_height: lineHeight }};
  }};
}})();
"""


def _build_context():
    """Boots one V8 isolate with mermaid.js loaded and ready to render.
    Only ever called *inside* the child process (see _child_main)."""
    from py_mini_racer import MiniRacer

    ctx = MiniRacer()
    ctx.eval("globalThis.__log = (s) => {};")
    ctx.eval(_measure_text_js())
    for script in context_scripts():
        ctx.eval(script)
    return ctx


# The page is rendered again while its <foreignObject> labels still had rough sizes. Real diagrams settle in two
# passes: a label's HTML does not depend on the size anything else was given.
_MAX_PASSES = 8
# Sizes learned so far, for the life of the child process: the next diagram that has the same label needs no extra pass.
_KNOWN_LIMIT = 50_000


def _render(ctx, code: str, theme: str, config: Optional[dict], css: Optional[str],
            known: dict, measure, build_context) -> str:
    """Renders until the page has asked for no <foreignObject> size it was not given exactly. `ctx` is the fresh
    context for the first pass, `build_context()` makes the one for each pass after it, `known` maps what the page
    asked (its own key for it) to novasvg's answer, and `measure(*what_was_asked)` asks novasvg."""
    if len(known) > _KNOWN_LIMIT:
        known.clear()
    for _ in range(_MAX_PASSES):
        ctx.eval(f"globalThis.__foKnown = {json.dumps(known)};")
        ctx.eval(render_script(code, theme, config, css))
        run_event_loop(ctx.eval)
        asked = json.loads(ctx.eval("JSON.stringify(globalThis.__foMissing)"))
        if not asked:
            return collect_svg(ctx.eval)
        # Whatever the page did with rough sizes (even fail) is not its answer: measure and go again.
        for key, what in asked.items():
            known[key] = measure(*what)
        ctx = build_context()
    raise MermaidRenderError(f"the sizes of the <foreignObject> labels did not settle in {_MAX_PASSES} passes")


def _child_main(conn) -> None:
    """
    Entry point of the child process (see Engine -- one child == one V8
    isolate). Boots V8 once, then serves render requests from the parent
    over `conn` until told to stop or the pipe closes. Never returns
    normally except on shutdown -- if this hangs, the parent's only
    recourse is killing the process outright (see module docstring), which
    is exactly the point: nothing in here needs to handle that gracefully.
    """
    known: dict = {}
    measurer = TextMeasurer()
    try:
        ctx = _build_context()
        conn.send(("ready", None))
    except Exception as exc:  # noqa: BLE001 -- report *any* boot failure to the parent
        conn.send(("boot_error", f"{type(exc).__name__}: {exc}"))
        return

    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return  # parent went away
        if msg is None:  # shutdown sentinel
            return

        code, theme, config, css = msg
        try:
            svg = _render(ctx, code, theme, config, css, known, measurer.foreign_object, _build_context)
            conn.send(("ok", svg))
        except MermaidRenderError as exc:
            conn.send(("render_error", str(exc)))
        except Exception as exc:  # noqa: BLE001 -- report *any* other failure to the parent
            conn.send(("render_error", f"{type(exc).__name__}: {exc}"))
        # A browser starts every page from zero (mermaid.js keeps module-level id counters), and
        # mermaid-cli opens a new page per diagram: the next render gets a context of its own.
        # Built right after replying, so it is ready while the caller is busy with the result.
        try:
            ctx = _build_context()
        except Exception as exc:  # noqa: BLE001
            conn.send(("boot_error", f"{type(exc).__name__}: {exc}"))
            return


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

        if not parent_conn.poll(timeout=_BOOT_TIMEOUT_MS / 1000):
            process.kill()
            raise MermaidRenderError(
                f"V8 engine failed to boot within {_BOOT_TIMEOUT_MS}ms."
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
