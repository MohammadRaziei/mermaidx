"""A mermaid label in wrap mode is `display:table; width:120px`. In a browser that width is only a minimum: the label
grows to its longest unbreakable word, and its text wraps again at the new width (issue #56)."""
import re

import mermaidx
from mermaidx.font_metrics import get_font

WORD = "Supercalifragilisticexpialidocious"
SRC = f'flowchart TD\n  a["one two three four five six seven {WORD} eight nine"]\n'


def _label_box(svg):
    m = re.search(r'<foreignObject width="([\d.]+)" height="([\d.]+)"', svg)
    return float(m.group(1)), float(m.group(2))


def _lines_at(width, text):
    html = ('<div xmlns="http://www.w3.org/1999/xhtml" style="display: table; white-space: break-spaces; line-height: 1.5; '
            f'max-width: {width}px; text-align: center; width: {width}px;"><span class="nodeLabel"><p>{text}</p></span></div>')
    return get_font("normal").foreign_object_metrics(html, 14)


def test_label_grows_to_its_longest_word():
    width, _ = _label_box(mermaidx.render(SRC).svg())
    word = get_font("normal").foreign_object_metrics(
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="white-space: nowrap;"><p>{WORD}</p></div>', 14)["width"]
    assert width > 120
    assert width >= word - 0.1


def test_label_text_wraps_again_at_the_grown_width():
    width, height = _label_box(mermaidx.render(SRC).svg())
    text = f"one two three four five six seven {WORD} eight nine"
    at_grown = _lines_at(width, text)
    at_120 = _lines_at(120, text)
    assert at_grown["line_count"] < at_120["line_count"]       # the wider box needs fewer lines
    assert height == at_grown["height"]                         # and the box is as tall as those lines
