"""
mermaidx.ascii — ASCII/Unicode terminal rendering.

Backed by termaid (https://pypi.org/project/termaid/): pure Python, ~700KB,
zero dependencies of its own -- small enough next to quickjs-ng/resvg that
it's a core dependency here rather than an optional extra. No binary blob
and no second JS engine to load, unlike the alternatives (mermaid-ascii is
a Go binary rebundled for PyPI by a third-party repackaging project;
beautiful-mermaid is a JS bundle that would need its own DOM shim loaded
into the QuickJS engine).

Character-cell art doesn't need real font metrics the way SVG layout does,
so this is a completely separate, lightweight code path from the
'quickjs'/'v8' backend rather than something built on top of it.
"""

from __future__ import annotations

import termaid


def render_ascii(source: str, **opts) -> str:
    """
    Render a Mermaid diagram as ASCII/Unicode box-drawing art.

    Args:
        source: Mermaid source text.
        **opts: Forwarded to termaid.render(), e.g. use_ascii=True,
                padding_x, padding_y, gap.

    Returns:
        The rendered diagram as a string, ending in a trailing newline.
    """
    art = termaid.render(source, **opts)
    # termaid.render() itself doesn't end with "\n" -- the termaid *CLI*
    # only appears to include one because printing a string adds one for
    # free. mermaidx.save()/diagram.py write this straight to a file with
    # no such implicit newline, so without this the saved file is missing
    # its trailing newline (unlike running `termaid` directly, and unlike
    # every other text file convention) -- reported as a diff-only
    # difference against `termaid`'s own output for the same diagram.
    if not art.endswith("\n"):
        art += "\n"
    return art
