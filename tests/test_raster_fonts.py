"""The text of a PNG is painted in the font the layout was measured with, whatever fonts the host has."""

from __future__ import annotations

import mermaidx

LONG_LABEL = (
    "graph TD\n"
    "    A[This is a very long label that should wrap across several lines when the maximum text width is reached "
    "by the layout engine] --> B[Short]\n"
)


def test_png_uses_the_measured_font_not_the_font_stack_of_the_svg():
    """mermaid.js writes "trebuchet ms", verdana, arial (or "Recursive Variable", arial) into the SVG. If novasvg
    resolved those names to a font of the host, the label would take fewer lines than the box was sized for."""
    svg = mermaidx.render(LONG_LABEL, backend="js:mermaid").svg()
    forced = svg
    for stack in ('"Recursive Variable",arial,sans-serif', '"trebuchet ms",verdana,arial,sans-serif'):
        forced = forced.replace(stack, '"DejaVu Sans"')
    assert forced != svg, "the SVG no longer names mermaid.js's own font stack, so this test has nothing to check"
    assert mermaidx.svg_to_png(svg, background="#ffffff") == mermaidx.svg_to_png(forced, background="#ffffff")
