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
