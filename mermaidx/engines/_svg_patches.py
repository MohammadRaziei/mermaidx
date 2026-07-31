"""Post-render SVG fixups shared by every JS engine (quickjs_engine.py,
v8_engine.py, ...).

Done here in Python rather than in dom_shim.js: benchmarked on a ~40KB
mindmap SVG, this regex substitution runs in ~7us via Python's `re`
(C-optimized) vs ~25us doing the equivalent `.replace()` call in
QuickJS-ng (no JIT) plus marshaling the result back across the Python/JS
boundary. Negligible either way next to render time itself, but there's
no offsetting reason (unlike the &nbsp; decode fix in dom_shim.js, which
has to run before XML-escaping to be correct) to pay it in the slower
place.
"""

from __future__ import annotations

import re


def patch_journey_task_text_color(svg: str) -> str:
    """https://github.com/MohammadRaziei/mermaidx/issues/31

    Journey/timeline diagrams default to `textPlacement: "fo"`, which
    places every section/task/actor label inside a
    `<foreignObject><div>` -- HTML that resvg (the engine this project
    rasterizes with) cannot render at all, so the labels vanished
    entirely. mermaidx forces `textPlacement` away from "fo" so mermaid
    falls back to its native `<text>`/`<tspan>` renderer instead.

    That fallback renderer sets each label's `fill` from the diagram's
    `sectionColours` theme array, which defaults to a single `"#fff"`
    entry. In mermaid's own foreignObject path that value is irrelevant
    -- the visible HTML text is colored by the ".label{color:#333}" CSS
    rule instead -- but in the native-text mode this engine requires it
    becomes the actual (invisible, white-on-pastel) rendered color.
    Overriding `sectionColours` via config isn't a clean fix either:
    mermaid concatenates rather than replaces array-valued config, so a
    single-entry override still leaves earlier sections cycling back to
    the original white default. Patched directly via CSS instead, scoped
    to the journey/timeline task and section label text.

    The section-header labels need `!important`: they share a
    "section-type-N" class with their own background <rect>, and
    mermaid's generated theme CSS sets that class's fill under an
    `#<diagramId> .section-type-N` selector -- higher specificity (an ID
    scope) than a bare `text.journey-section` rule -- which repaints the
    label the same pastel color as its own box, i.e. invisible again.
    """
    if "<style" in svg and (".task-type-" in svg or ".journey-section" in svg or "timeline-node" in svg):
        svg = re.sub(
            r"(<style[^>]*>)",
            r"\1text.task,text.journey-section,.timeline-node text{fill:#333 !important;}",
            svg,
            count=1,
        )
    return svg


def patch_mindmap_centering(svg: str) -> str:
    """mermaid's own mindmap CSS defines centering via a
    ".mindmap-node-label{text-anchor:middle;...}" rule, but (only in the
    native-SVG-text mode this engine requires -- resvg can't render the
    foreignObject+HTML labels mermaid uses by default) never actually
    attaches that class to any element, so the rule is dead and labels
    render left-anchored instead of centered. Patched in directly since we
    can't change mermaid.js's own class-assignment logic; scoped to
    mindmap nodes only."""
    if "<style" in svg and "section-root" in svg:
        svg = re.sub(
            r"(<style[^>]*>)",
            r"\1.section-root .label text{text-anchor:middle;}",
            svg,
            count=1,
        )
    return svg
