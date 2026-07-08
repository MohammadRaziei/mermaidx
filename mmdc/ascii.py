"""
mmdc.ascii — optional ASCII/Unicode terminal rendering.

Backed by termaid (https://pypi.org/project/termaid/): pure Python, zero
dependencies, no binary blob and no second JS engine to load — unlike the
alternatives (mermaid-ascii is a Go binary rebundled for PyPI by a
third-party repackaging project; beautiful-mermaid is a JS bundle that would
need its own DOM shim loaded into the QuickJS engine). Character-cell art
doesn't need real font metrics the way SVG layout does, so this is
intentionally a completely separate, lightweight code path from the 'js'
backend rather than a method on Diagram.
"""

from __future__ import annotations


def render_ascii(source: str, **opts) -> str:
    """
    Render a Mermaid diagram as ASCII/Unicode box-drawing art.

    Requires the optional ``termaid`` package::

        pip install mmdc[ascii]

    Args:
        source: Mermaid source text.
        **opts: Forwarded to termaid.render(), e.g. use_ascii=True,
                padding_x, padding_y, gap.

    Returns:
        The rendered diagram as a string.
    """
    try:
        import termaid
    except ImportError as exc:
        raise ImportError(
            "render_ascii() requires the optional 'termaid' package. "
            "Install it with:\n    pip install mmdc[ascii]"
        ) from exc
    return termaid.render(source, **opts)
