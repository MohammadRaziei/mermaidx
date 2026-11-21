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


def test_code_in_a_label_is_measured_with_the_bundled_monospace_face():
    """<code> takes the generic `monospace` family; mermaidx registers its own DejaVu Sans Mono under that name, so the
    label is as wide as that face says on every host."""
    import pytest
    import novasvg.fonts as fonts
    from mermaidx.font_metrics import get_font

    def width(inner):
        html = ('<div xmlns="http://www.w3.org/1999/xhtml" style="display: table-cell; white-space: nowrap; '
                f'line-height: 1.5;"><span><p>{inner}</p></span></div>')
        return get_font("normal").foreign_object_metrics(html, 16)["width"]

    text = "promise_type promise {};"
    if width(text) == width(f"<code>{text}</code>"):
        pytest.skip("this novasvg measures <code> like plain text (monospace support needs a newer novasvg)")
    mono = fonts.Font(fonts.get_font_face("monospace", False, False), 16.0)
    assert width(f"<code>{text}</code>") == pytest.approx(mono.measure_text(text), abs=0.1)
