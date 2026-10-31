"""
What the QuickJS and V8 engines have in common, written once.

The engines differ only in how they run JS (and how text measurement gets back into Python); everything they
run -- which scripts load in which order, the mermaid config, the page script that renders like mermaid-cli --
is defined here, so a change to it cannot reach one engine and miss the other.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from mermaidx.font_metrics import get_font
from mermaidx.path_bbox import PATH_BBOX_JS

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

# mermaid-cli's defaults: the svg's id, and the background it paints (`-b transparent`).
RENDER_ID = "my-svg"
BACKGROUND = "transparent"

# The JS libraries an engine can run (the `js:<library>` backends, see mermaidx.backends).
LIBRARIES = ("mermaid", "pele")


class MermaidRenderError(RuntimeError):
    """Raised when mermaid.js itself reports a parse/render error."""


_ESM_EXPORT = re.compile(r"export\s*\{([^}]*)\}\s*;?\s*$")


def esm_to_global(source: str, name: str) -> str:
    """Turns an ES module that ends in one `export{a as b,...};` (a bundler's output, like pele.js from jsdelivr)
    into a classic script that defines `globalThis[name]` -- the engines evaluate scripts, not modules. The module
    body goes in a function, so its top-level `var`s do not leak into the page's global scope."""
    m = _ESM_EXPORT.search(source)
    if m is None:
        raise ValueError(f"{name}: expected the module to end in `export{{...}};`")
    pairs = []
    for item in m.group(1).split(","):
        local, _, exported = item.strip().partition(" as ")
        pairs.append(f"{(exported or local).strip()}:{local.strip()}")
    return f"globalThis.{name}=(function(){{{source[:m.start()]}\nreturn {{{','.join(pairs)}}};}})();"


@lru_cache(maxsize=None)
def context_scripts(library: str = "mermaid") -> tuple[str, ...]:
    """The JS every fresh context evaluates, in order, after the engine has installed its own `__log` and
    `__measure*` hooks.

    mermaid: path geometry, the DOM shim (which calls both), mermaid.js, the `mermaid` global, and the page
    script of mermaid-cli (`__renderLikeMmdc`).
    pele: just pele.js (an ES module, made a global here) -- it is synchronous and needs no DOM."""
    read = lambda name: (_ASSETS_DIR / name).read_text(encoding="utf-8")  # noqa: E731
    if library == "pele":
        return (esm_to_global(read("pele.js"), "pele"),)
    if library != "mermaid":
        raise ValueError(f"Unknown JS library {library!r}; expected one of {LIBRARIES}.")
    return (
        PATH_BBOX_JS,
        read("dom_shim.js"),
        read("mermaid.js"),
        "globalThis.mermaid = (globalThis.__esbuild_esm_mermaid_nm.mermaid.default"
        " || globalThis.__esbuild_esm_mermaid_nm.mermaid);",
        read("mmdc_driver.js"),
    )


def mermaid_config(theme: Optional[str], config: Optional[dict]) -> dict:
    """The config handed to mermaid.initialize().

    htmlLabels / textPlacement="fo" are mermaid.js's own defaults, set explicitly so they are the same whatever
    mermaid's version does: the label markup is real HTML in a <foreignObject>, which the shim sizes and novasvg
    paints. Any key the caller passes wins over these defaults."""
    cfg = {
        "startOnLoad": False,
        "flowchart": {"htmlLabels": True},
        "journey": {"textPlacement": "fo"},
        "timeline": {"textPlacement": "fo"},
    }
    # Like mmdc, no "theme" key unless one was asked for: mermaid >= 12 then gives every diagram type its own
    # default theme and look (e.g. flowcharts: redux-color / neo); an explicit "default" would force the old one.
    if theme:
        cfg["theme"] = theme
    if config:
        cfg.update(config)
    return cfg


def pele_render_script(code: str, config: Optional[dict]) -> str:
    """The pele counterpart of render_script(): pele.render() is synchronous, so the result (or the error) is
    set when the script returns. `.slice(0)` flattens the string for the QuickJS binding (see _FLATTEN_JS in
    quickjs_engine.py: a long concatenation reaches it as a rope otherwise)."""
    options = {"config": config} if config else {}
    return (
        "globalThis.__renderResult = null;\n"
        "globalThis.__renderError = null;\n"
        "try {\n"
        f"  globalThis.__renderResult = pele.render({json.dumps(code)}, {json.dumps(options)}).svg.slice(0);\n"
        "} catch (e) {\n"
        "  globalThis.__renderError = (e && e.name ? e.name + ': ' + e.message : String(e));\n"
        "}\n"
    )


def render_script(code: str, theme: Optional[str], config: Optional[dict], css: Optional[str],
                  library: str = "mermaid") -> str:
    """One script that starts a render in a fresh context: a clean document, mermaid.initialize(), the caller's
    CSS if any, then `__renderLikeMmdc`. It leaves `__renderResult` (the svg) or `__renderError` set once the
    returned promise settles. Every value goes in as a JSON literal, so any text is passed through unchanged.

    For library="pele" the script is pele_render_script() (theme and css are applied by the caller, in Python:
    pele is themed by CSS variables, not by a theme name)."""
    if library == "pele":
        return pele_render_script(code, config)
    css_block = ""
    if css:
        css_block = (
            "(function () {\n"
            "  var el = document.getElementById('mermaidx-css') || document.createElement('style');\n"
            "  el.setAttribute('id', 'mermaidx-css');\n"
            f"  el.textContent = {json.dumps(css)};\n"
            "  document.head.appendChild(el);\n"
            "})();\n"
        )
    return (
        "__resetDocument();\n"
        f"mermaid.initialize({json.dumps(mermaid_config(theme, config))});\n"
        f"{css_block}"
        "globalThis.__renderResult = null;\n"
        "globalThis.__renderError = null;\n"
        f"__renderLikeMmdc({json.dumps(RENDER_ID)}, {json.dumps(code)}, {json.dumps(BACKGROUND)})\n"
        "  .then(svg => { globalThis.__renderResult = svg; })\n"
        "  .catch(e => { globalThis.__renderError = (e && e.name ? e.name + ': ' + e.message : String(e)); });\n"
    )


class TextMeasurer:
    """Real font metrics via mermaidx.font_metrics (bundled DejaVu Sans) --
    the same font file mermaidx.raster (novasvg) is told to use for final
    rendering, so layout and paint always agree (see Engine._init_context /
    mermaidx.py)."""

    def width(self, text, size, family, weight, style) -> float:
        return get_font(weight).measure(text or "", float(size or 16))["width"]

    def full(self, text, size, family, weight, style) -> dict:
        return get_font(weight).measure(text or "", float(size or 16))

    def glyphs(self, text, size, family, weight, style) -> list:
        return get_font(weight).glyph_boxes(text or "", float(size or 16))

    def foreign_object(self, html, size, family, weight, style) -> dict:
        return get_font(weight).foreign_object_metrics(html or "", float(size or 16))


# Every step of the page's event loop is a promise job or a timer; this bounds a page that never stops scheduling.
MAX_EVENT_LOOP_STEPS = 200_000
_RENDER_DONE_JS = "!!globalThis.__renderResult || !!globalThis.__renderError"


def run_event_loop(evaluate: Callable[[str], object], run_job: Optional[Callable[[], bool]] = None) -> None:
    """Runs the page the way a browser does until the render has finished (a result or an error is set): all the
    promise jobs, then the next timer (dom_shim.js keeps them on a queue with a virtual clock), then all the jobs
    again, and so on. Stops early when the render is done -- a page that asks for a frame in every frame, as
    cytoscape's does, would otherwise keep it going for ever -- or when nothing is left that could finish it.

    `run_job` runs one pending promise job and says whether there was one: QuickJS hands them over one at a time.
    V8 has no such call: it drains them by itself at the end of every eval(), so it passes none."""
    for _ in range(MAX_EVENT_LOOP_STEPS):
        if evaluate(_RENDER_DONE_JS):
            return
        if run_job is not None and run_job():
            continue
        if not evaluate("__runNextTimer()"):
            return


def collect_svg(evaluate: Callable[[str], object]) -> str:
    """The svg a finished render left behind, or MermaidRenderError. `evaluate` is the context's eval()."""
    err = evaluate("globalThis.__renderError")
    if err:
        raise MermaidRenderError(str(err))
    svg = evaluate("globalThis.__renderResult")
    if not svg:
        raise MermaidRenderError("mermaid.render() produced no output (unknown error)")
    return str(svg)
