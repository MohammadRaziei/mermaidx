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

# A context is thrown away after every render because mermaid.js keeps state between renders that a browser would
# start from zero on every page load: module-level id counters (actor1, classId-Animal-0, ...) and the position in
# its pseudo-random sequence, which moves the hand-drawn shapes. pele.js keeps none: rendering all 43 samples of
# tests/samples in one context gives byte-for-byte the same SVG as a fresh context for each (tests/test_engine_common.py
# keeps checking this). A context is the whole cost of a pele render (about 100 ms to parse pele.js, against 1 ms to
# render), so pele's contexts are reused. Not forever: the context is replaced after this many renders, so whatever
# a long-running process might accumulate in it stays bounded.
CONTEXT_REUSE_LIMIT = 1000


def reuses_context(library: str, renders_so_far: int) -> bool:
    """True when a context that has rendered `renders_so_far` diagrams may render the next one as it is."""
    return library == "pele" and renders_so_far < CONTEXT_REUSE_LIMIT


class MermaidRenderError(RuntimeError):
    """Raised when mermaid.js itself reports a parse/render error."""


_ESM_EXPORT = re.compile(r"export\s*\{([^}]*)\}\s*;?\s*$")


def esm_to_global(source: str, name: str) -> str:
    """Turns an ES module that ends in one `export{a as b,...};` (a bundler's output, like pele.js from npm)
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


# A ZenUML diagram starts with `zenuml`, after the frontmatter and the `%%` directives and comments, which is where
# mermaid looks for it too. ZenUML is not part of mermaid's core: it is the separate package @mermaid-js/mermaid-zenuml,
# which draws HTML with React and needs a browser to measure it. So mermaidx does not use that package. It runs the
# SVG renderer that is inside the command line tool of @zenuml/core (assets/zenuml.js, built by
# tools/build_zenuml.sh), and hands it the text after the `zenuml` line, as the plugin does.
_FRONTMATTER = re.compile(r"\A\s*---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_DIRECTIVE_OR_COMMENT = re.compile(r"\A[ \t]*%%[^\n]*(?:\n|\Z)")
_ZENUML_HEADER = re.compile(r"\A\s*zenuml\b")


def zenuml_body(code: str) -> str | None:
    """The ZenUML text after the `zenuml` line if `code` is a ZenUML diagram, else None."""
    text = code
    match = _FRONTMATTER.match(text)
    if match:
        text = text[match.end():]
    while True:
        match = _DIRECTIVE_OR_COMMENT.match(text)
        if not match:
            break
        text = text[match.end():]
    match = _ZENUML_HEADER.match(text)
    return text[match.end():] if match else None


def needs_zenuml(code: str) -> bool:
    return zenuml_body(code) is not None


@lru_cache(maxsize=1)
def _zenuml_script() -> str:
    """assets/zenuml.js (built by tools/build_zenuml.sh): defines `__zenuml.renderToSvg`. 400 KB, so it is only part
    of the render script of a ZenUML diagram. It measures text with `document.createElement("canvas")`, which the DOM
    shim has, so the widths are the same real font metrics mermaid.js gets."""
    return (_ASSETS_DIR / "zenuml.js").read_text(encoding="utf-8")


def zenuml_render_script(body: str) -> str:
    """The ZenUML counterpart of render_script(): renderToSvg() is synchronous, so the result (or the error) is set
    when the script returns. Neither the theme nor the config applies to it: they are mermaid's, not ZenUML's."""
    return (
        f"{_zenuml_script()}\n"
        "__resetDocument();\n"
        "globalThis.__renderResult = null;\n"
        "globalThis.__renderError = null;\n"
        "try {\n"
        f"  const r = globalThis.__zenuml.renderToSvg({json.dumps(body)}, {{}});\n"
        "  if (!r || !r.width || !r.height) throw new Error('the ZenUML diagram is empty or could not be parsed');\n"
        "  globalThis.__renderResult = r.svg.slice(0);\n"
        "} catch (e) {\n"
        "  globalThis.__renderError = (e && e.name ? e.name + ': ' + e.message : String(e));\n"
        "}\n"
    )


# A diagram asks for the ELK layout with `flowchart-elk`, `layout: elk` (frontmatter), `%%{init: {"layout": "elk"}}%%`,
# or `config={"layout": "elk"}`; the other ELK algorithms are named `elk.stress`, `elk.force` and so on. All of them
# contain the word `elk`. A false positive only costs the time to load the script, so the test stays this simple.
_ELK_WORD = re.compile(r"\belk\b", re.IGNORECASE)


def needs_elk(code: str, config: dict | None = None) -> bool:
    """True if the diagram source or the config asks for the ELK layout (see the comment above)."""
    return bool(_ELK_WORD.search(code) or (config and _ELK_WORD.search(json.dumps(config, default=str))))


@lru_cache(maxsize=1)
def _elk_script() -> str:
    """assets/layout_elk.js (built by tools/build_layout_elk.sh): registers the ELK layout on the `mermaid` global.
    It is 2.4 MB, so it is not part of every context, only of the render script of a diagram that needs it."""
    return (_ASSETS_DIR / "layout_elk.js").read_text(encoding="utf-8")


def render_script(code: str, theme: Optional[str], config: Optional[dict], css: Optional[str],
                  library: str = "mermaid") -> str:
    """One script that starts a render in a fresh context: a clean document, mermaid.initialize(), the caller's
    CSS if any, then `__renderLikeMmdc`. It leaves `__renderResult` (the svg) or `__renderError` set once the
    returned promise settles. Every value goes in as a JSON literal, so any text is passed through unchanged.

    For library="pele" the script is pele_render_script() (theme and css are applied by the caller, in Python:
    pele is themed by CSS variables, not by a theme name; it has no ELK layout and ignores a request for it).
    For a diagram that needs the ELK layout (see needs_elk), the ELK script comes first. A ZenUML diagram does not go
    through mermaid.js at all: zenuml_render_script() (the theme, the config and the css do not apply to it)."""
    if library == "pele":
        return pele_render_script(code, config)
    body = zenuml_body(code)
    if body is not None:
        return zenuml_render_script(body)
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
    elk = _elk_script() + "\n" if needs_elk(code, config) else ""
    return (
        f"{elk}"
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
