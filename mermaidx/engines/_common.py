"""
What the QuickJS and V8 engines have in common, written once.

The engines differ only in how they run JS (and how text measurement gets back into Python); everything they
run -- which scripts load in which order, the mermaid config, the page script that renders like mermaid-cli --
is defined here, so a change to it cannot reach one engine and miss the other.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from mermaidx.path_bbox import PATH_BBOX_JS

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

# mermaid-cli's defaults: the svg's id, and the background it paints (`-b transparent`).
RENDER_ID = "my-svg"
BACKGROUND = "transparent"


class MermaidRenderError(RuntimeError):
    """Raised when mermaid.js itself reports a parse/render error."""


@lru_cache(maxsize=1)
def context_scripts() -> tuple[str, ...]:
    """The JS every fresh context evaluates, in order, after the engine has installed its own `__log` and
    `__measure*` hooks: path geometry, the DOM shim (which calls both), mermaid.js, the `mermaid` global, and
    the page script of mermaid-cli (`__renderLikeMmdc`)."""
    read = lambda name: (_ASSETS_DIR / name).read_text(encoding="utf-8")  # noqa: E731
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
        "theme": theme or "default",
        "flowchart": {"htmlLabels": True},
        "journey": {"textPlacement": "fo"},
        "timeline": {"textPlacement": "fo"},
    }
    if config:
        cfg.update(config)
    return cfg


def render_script(code: str, theme: Optional[str], config: Optional[dict], css: Optional[str]) -> str:
    """One script that starts a render in a fresh context: a clean document, mermaid.initialize(), the caller's
    CSS if any, then `__renderLikeMmdc`. It leaves `__renderResult` (the svg) or `__renderError` set once the
    returned promise settles. Every value goes in as a JSON literal, so any text is passed through unchanged."""
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


def collect_svg(evaluate: Callable[[str], object]) -> str:
    """The svg a finished render left behind, or MermaidRenderError. `evaluate` is the context's eval()."""
    err = evaluate("globalThis.__renderError")
    if err:
        raise MermaidRenderError(str(err))
    svg = evaluate("globalThis.__renderResult")
    if not svg:
        raise MermaidRenderError("mermaid.render() produced no output (unknown error)")
    return str(svg)
