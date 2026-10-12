"""foreignObject label sizes: bold and italic runs are measured with the faces novasvg paints them with.
Chrome (the reference): 'Group one' with a bold 'Group' is 89.72 wide, 83.57 with none."""
import pytest

from mermaidx.font_metrics import get_font


def _width(font, html, size=16.0):
    return font.foreign_object_metrics(f"<div>{html}</div>", size)["width"]


def test_a_bold_run_is_measured_with_the_bold_face():
    regular, bold = get_font(None), get_font("bold")
    assert _width(regular, "Group one") == pytest.approx(regular.measure("Group one", 16)["width"])
    assert _width(regular, "<strong>Group</strong> one") == pytest.approx(
        bold.measure("Group", 16)["width"] + regular.measure(" one", 16)["width"])
    assert _width(regular, "<strong>Group</strong> one") == pytest.approx(89.72, abs=0.01)  # Chrome


def test_b_and_strong_measure_alike():
    regular = get_font(None)
    assert _width(regular, "<b>Group</b> one") == _width(regular, "<strong>Group</strong> one")


def test_unstyled_text_in_a_bold_label_is_bold():
    bold = get_font("bold")
    assert _width(bold, "Group one") == pytest.approx(bold.measure("Group one", 16)["width"])
