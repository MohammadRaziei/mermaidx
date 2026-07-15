"""
mermaidx.engine — headless Mermaid → SVG rendering without a browser.

Architecture
------------
mermaid.js (v11, ES2020+) is executed inside QuickJS-ng (a small, actively
maintained JS engine — NOT the browser-less-but-limited original QuickJS,
which lacks class static blocks used by mermaid's dependencies).

Since QuickJS has no DOM, a minimal fake DOM/SVG implementation is loaded
first (assets/dom_shim.js). The one piece a fake DOM cannot fabricate on its
own — real text metrics (`getBBox` / `getComputedTextLength`) — is bridged
back into Python, where mermaidx.font_metrics reads real glyph advance widths
from a bundled font file (DejaVu Sans). The same font file is handed to
resvg for final rendering (see mermaidx.py), so the layout mermaid computes
always matches what actually gets painted — by construction, not by luck.

A dedicated single-thread executor owns the QuickJS context, since QuickJS
contexts are not thread-safe and must always be driven from one thread.
"""

from __future__ import annotations

import json
import math
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import quickjs

from mermaidx.font_metrics import get_font

_ASSETS_DIR = Path(__file__).parent / "assets"
_DOM_SHIM_JS = _ASSETS_DIR / "dom_shim.js"
_MERMAID_JS = _ASSETS_DIR / "mermaid.js"

_RENDER_TIMEOUT_JOBS = 200_000  # safety cap on Promise-job pump iterations


class MermaidRenderError(RuntimeError):
    """Raised when mermaid.js itself reports a parse/render error."""


class _TextMeasurer:
    """Real font metrics via mermaidx.font_metrics (bundled DejaVu Sans) —
    the same font file resvg is told to use for final rendering, so layout
    and paint always agree (see Engine._init_context / mermaidx.py)."""

    def width(self, text, size, family, weight, style) -> float:
        return get_font(weight).measure(text or "", float(size or 16))["width"]

    def full(self, text, size, family, weight, style) -> dict:
        return get_font(weight).measure(text or "", float(size or 16))


_PATH_CMD_CHARS = set("MmLlHhVvCcSsQqTtAaZz")
_PATH_NUM_RE = re.compile(r"-?\d*\.\d+(?:[eE][-+]?\d+)?|-?\d+(?:[eE][-+]?\d+)?")
_PATH_ARGC = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _arc_extrema(x1, y1, rx, ry, rot_deg, large_arc, sweep, x2, y2):
    """Points bounding an SVG elliptical-arc segment: the two endpoints plus
    any axis-aligned extrema the arc actually sweeps through, via the
    standard endpoint-to-center parameterization (SVG 1.1 appendix F.6).
    Degenerate/rotated-ellipse edge cases fall back to a padded box around
    the endpoints rather than getting the extrema wrong.
    """
    if rx == 0 or ry == 0:
        return [(x1, y1), (x2, y2)]
    phi = math.radians(rot_deg % 360)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    # endpoint -> center parameterization
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    rxsq, rysq = rx * rx, ry * ry
    num = rxsq * rysq - rxsq * y1p * y1p - rysq * x1p * x1p
    denom = rxsq * y1p * y1p + rysq * x1p * x1p
    if denom == 0:
        return [(x1, y1), (x2, y2)]
    co = math.sqrt(max(0.0, num / denom))
    if large_arc == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        if d == 0:
            return 0.0
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = math.acos(c)
        return -a if ux * vy - uy * vx < 0 else a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    theta2 = theta1 + dtheta

    pts = [(x1, y1), (x2, y2)]
    lo, hi = min(theta1, theta2), max(theta1, theta2)
    # candidate extrema angles: where the (unrotated) ellipse has a
    # horizontal or vertical tangent -- 0/pi give the x-extrema, pi/2 &
    # 3pi/2 give the y-extrema. Only ones actually inside the swept range
    # count. Only exact for rot_deg == 0 (mermaid never rotates its arcs);
    # for a genuinely rotated ellipse this under-covers slightly, which is
    # an acceptably rare, acceptably small imprecision for a layout bbox.
    for k in range(4):
        ang = k * math.pi / 2
        a = ang
        while a < lo:
            a += 2 * math.pi
        if a <= hi:
            pts.append((cx + rx * math.cos(a) * cos_p - ry * math.sin(a) * sin_p,
                        cy + rx * math.cos(a) * sin_p + ry * math.sin(a) * cos_p))
    return pts


def _path_bbox(d: str) -> dict:
    """Bbox from an SVG path's `d` string, via a real (if minimal) parser.

    A previous version just grabbed every number in the string and treated
    them as alternating x/y pairs. That only works for M/L/C-only paths.
    Mermaid's own shape library (cylinders, stadiums, rounded-rect corners)
    draws with `A` (elliptical arc: rx,ry,rotation,large-arc,sweep,x,y — 7
    args) and `H`/`V` (single-coordinate lineto). Any of those desyncs a
    flat even/odd split for every number after it, silently corrupting the
    bbox for the rest of the path — which is what was clipping cylinder/
    stadium-shaped nodes off the edge of the final SVG.

    Exact geometry isn't the goal (this only feeds getBBox() for layout),
    so bezier control points are folded in as extra points around the
    endpoints -- a deliberately generous, conservative box rather than a
    tight one -- but arcs get their true extrema (see _arc_extrema) since
    they're common enough in mermaid's shape library to be worth doing
    properly rather than padding generously.
    """
    if not d:
        return {"x": 0, "y": 0, "width": 0, "height": 0}

    xs: list[float] = []
    ys: list[float] = []
    cx = cy = 0.0
    start_x = start_y = 0.0
    cmd = None
    i, n = 0, len(d)
    first_pair_of_cmd = True
    while i < n:
        ch = d[i]
        if ch in _PATH_CMD_CHARS:
            cmd = ch
            first_pair_of_cmd = True
            i += 1
            continue
        if ch.isspace() or ch == ",":
            i += 1
            continue
        if cmd is None:
            i += 1
            continue
        if cmd.upper() == "Z":
            cx, cy = start_x, start_y
            xs.append(cx)
            ys.append(cy)
            cmd = None
            continue

        argc = _PATH_ARGC[cmd.upper()]
        is_rel = cmd.islower()
        group: list[float] = []
        while len(group) < argc:
            m = _PATH_NUM_RE.match(d, i)
            if not m:
                break
            group.append(float(m.group()))
            i = m.end()
            while i < n and (d[i].isspace() or d[i] == ","):
                i += 1
        if len(group) < argc:
            break  # malformed tail -- stop rather than misparse

        effective_cmd = cmd.upper()
        if effective_cmd == "M" and not first_pair_of_cmd:
            effective_cmd = "L"  # subsequent pairs after M are implicit lineto

        if effective_cmd == "H":
            nx = cx + group[0] if is_rel else group[0]
            ny = cy
            xs.append(nx); ys.append(ny)
        elif effective_cmd == "V":
            nx = cx
            ny = cy + group[0] if is_rel else group[0]
            xs.append(nx); ys.append(ny)
        elif effective_cmd == "A":
            rx, ry, rot, laf, sf, ex, ey = group
            nx = cx + ex if is_rel else ex
            ny = cy + ey if is_rel else ey
            rx, ry = abs(rx), abs(ry)
            pts = _arc_extrema(cx, cy, rx, ry, rot, laf, sf, nx, ny)
            xs.extend(p[0] for p in pts)
            ys.extend(p[1] for p in pts)
        else:  # M, L, C, S, Q, T
            for k in range(0, len(group), 2):
                px, py = group[k], group[k + 1]
                if is_rel:
                    px += cx
                    py += cy
                xs.append(px)
                ys.append(py)
            nx, ny = xs[-1], ys[-1]

        cx, cy = nx, ny
        if effective_cmd == "M":
            start_x, start_y = cx, cy
        first_pair_of_cmd = False

    if not xs:
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


# ── Engine ───────────────────────────────────────────────────────────────────

class Engine:
    """
    One Engine = one QuickJS context with mermaid.js loaded, pinned to one
    dedicated worker thread. Reused across many renders (loading mermaid.js
    itself, ~6MB of source, is the expensive part — do it once).
    """

    def __init__(self) -> None:
        self._executor: Optional[ThreadPoolExecutor] = None
        self._ctx: Optional[quickjs.Context] = None
        self._measurer: Optional[_TextMeasurer] = None
        self._render_count = 0
        self._lock = threading.Lock()

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        if self._executor is not None:
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mermaidx-engine")
        self._executor.submit(self._init_context).result()

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
        self._measurer = _TextMeasurer()
        ctx = quickjs.Context()
        ctx.set_memory_limit(512 * 1024 * 1024)
        # NOTE: no ctx.set_time_limit() — quickjs forbids calling back into
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
        ctx.add_callable("__pathBBox_raw", lambda d: json.dumps(_path_bbox(d)))

        ctx.eval(
            "globalThis.__log = (s) => __log_raw(s);\n"
            "globalThis.__measureText = (t,s,f,w,st) => __measureText_raw(t,s,f,w,st);\n"
            "globalThis.__measureTextFull = (t,s,f,w,st) => JSON.parse(__measureTextFull_raw(t,s,f,w,st));\n"
            "globalThis.__pathBBox = (d) => JSON.parse(__pathBBox_raw(d));\n"
        )

        ctx.eval(_DOM_SHIM_JS.read_text(encoding="utf-8"))
        ctx.eval(_MERMAID_JS.read_text(encoding="utf-8"))
        ctx.eval(
            "globalThis.mermaid = (globalThis.__esbuild_esm_mermaid_nm.mermaid.default"
            " || globalThis.__esbuild_esm_mermaid_nm.mermaid);"
        )
        self._ctx = ctx

    def _pump_jobs(self, stop_when: Optional[str] = None) -> None:
        """Drain the Promise/microtask queue. If `stop_when` is a JS boolean
        expression, stop as soon as it's true rather than draining the whole
        job queue. Some diagrams (mindmap, via cytoscape) keep an internal
        render loop scheduled indefinitely via requestAnimationFrame, built
        for a long-lived interactive page, that never naturally empties the
        job queue on its own in a one-shot headless render."""
        assert self._ctx is not None
        for _ in range(_RENDER_TIMEOUT_JOBS):
            if stop_when is not None and self._ctx.eval(stop_when):
                return
            try:
                if not self._ctx.execute_pending_job():
                    return
            except StopIteration:
                return

    def _render_svg_sync(self, code: str, theme: str, config: Optional[dict], css: Optional[str]) -> str:
        assert self._ctx is not None
        ctx = self._ctx
        self._render_count += 1
        render_id = f"gd{self._render_count}"

        base_config = {"startOnLoad": False, "theme": theme or "default",
                        "flowchart": {"htmlLabels": False}, "htmlLabels": False}
        if config:
            base_config.update(config)

        ctx.eval("__resetDocument();")
        ctx.set("__config", json.dumps(base_config))
        ctx.eval("mermaid.initialize(JSON.parse(__config));")

        if css:
            ctx.set("__css", css)
            ctx.eval(
                "(function(){"
                "  var el = document.getElementById('mermaidx-css') || document.createElement('style');"
                "  el.setAttribute('id', 'mermaidx-css');"
                "  el.textContent = __css;"
                "  document.head.appendChild(el);"
                "})();"
            )

        ctx.set("__code", code)
        ctx.set("__renderId", render_id)
        ctx.eval(
            "globalThis.__renderResult = null;\n"
            "globalThis.__renderError = null;\n"
            "mermaid.render(__renderId, __code)\n"
            "  .then(r => { globalThis.__renderResult = r.svg; })\n"
            "  .catch(e => { globalThis.__renderError = (e && e.name ? e.name+': '+e.message : String(e)); });\n"
        )
        self._pump_jobs(stop_when="!!globalThis.__renderResult || !!globalThis.__renderError")

        err = ctx.eval("globalThis.__renderError")
        if err:
            raise MermaidRenderError(str(err))
        svg = ctx.eval("globalThis.__renderResult")
        if not svg:
            raise MermaidRenderError("mermaid.render() produced no output (unknown error)")
        svg = str(svg)
        # mermaid's own mindmap CSS defines centering via a
        # ".mindmap-node-label{text-anchor:middle;...}" rule, but (only in
        # the native-SVG-text mode this engine requires -- resvg can't
        # render the foreignObject+HTML labels mermaid uses by default)
        # never actually attaches that class to any element, so the rule
        # is dead and labels render left-anchored instead of centered.
        # Patched in directly since we can't change mermaid.js's own
        # class-assignment logic; scoped to mindmap nodes only.
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
        if self._executor is None:
            raise RuntimeError("Engine is not started.")
        return self._executor.submit(self._render_svg_sync, code, theme, config, css).result()
