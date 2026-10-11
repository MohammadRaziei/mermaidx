"""The element-by-element SVG comparison used against mmdc's references (tests/svg_compare.py)."""
import pytest

import svg_compare as sc


def _svg(body, attrs=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg"{attrs}>{body}</svg>'


def test_identical_documents_have_no_differences():
    s = _svg('<g id="a" class="x"><text>hi &amp; bye</text><path d="M0 0L1 1"/></g>')
    assert sc.compare(sc.parse(s), sc.parse(s)) == []


def test_attribute_order_is_not_a_difference():
    a = _svg('<rect x="1" y="2"/>')
    b = _svg('<rect y="2" x="1"/>')
    assert sc.compare(sc.parse(a), sc.parse(b)) == []


def test_numbers_are_compared_approximately_inside_any_attribute():
    a = _svg('<path d="M91.346875 10L5.5,6"/>', ' viewBox="0 -4.144548416 600 404.14456"')
    b = _svg('<path d="M91.34687690734863 10L5.5,6"/>', ' viewBox="0 -4.144547939 600 404.14456"')
    assert sc.compare(sc.parse(a), sc.parse(b)) == []


def test_a_number_beyond_the_tolerance_is_reported_with_its_place():
    a = _svg('<g><path id="p" d="M10 10L20 20"/></g>')
    b = _svg('<g><path id="p" d="M10 10L20 21"/></g>')
    diffs = sc.compare(sc.parse(a), sc.parse(b))
    assert len(diffs) == 1 and "path" in diffs[0] and "d" in diffs[0] and "20 21" in diffs[0]


def test_text_around_the_numbers_must_match_exactly():
    a = _svg('<rect style="width: 10px; fill: red"/>')
    b = _svg('<rect style="width: 10px; fill: blue"/>')
    assert sc.compare(sc.parse(a), sc.parse(b))


def test_different_tag_missing_attribute_and_extra_child_are_reported():
    assert sc.compare(sc.parse(_svg("<g/>")), sc.parse(_svg("<a/>")))
    assert sc.compare(sc.parse(_svg('<g id="a"/>')), sc.parse(_svg("<g/>")))
    assert sc.compare(sc.parse(_svg("<g/>")), sc.parse(_svg("<g/><g/>")))


def test_text_content_is_compared_and_numbers_in_it_are_approximate():
    assert sc.compare(sc.parse(_svg("<text>x 1.00000001</text>")), sc.parse(_svg("<text>x 1</text>"))) == []
    assert sc.compare(sc.parse(_svg("<text>hello</text>")), sc.parse(_svg("<text>world</text>")))


def test_children_are_compared_in_order():
    assert sc.compare(sc.parse(_svg("<a/><b/>")), sc.parse(_svg("<b/><a/>")))


def test_tolerance_is_a_parameter():
    a, b = sc.parse(_svg('<rect x="100"/>')), sc.parse(_svg('<rect x="100.5"/>'))
    assert sc.compare(a, b)
    assert sc.compare(a, b, rel_tol=1e-2) == []


def test_random_ids_are_masked():
    a = '<svg xmlns="http://www.w3.org/2000/svg" id="my-svg-state-id-abc12-3"/>'
    b = '<svg xmlns="http://www.w3.org/2000/svg" id="my-svg-state-id-zz9x-3"/>'
    assert sc.compare(sc.parse(sc.mask_random_ids(a)), sc.parse(sc.mask_random_ids(b))) == []


def test_not_xml_raises():
    with pytest.raises(Exception):
        sc.parse("<svg><g></svg>")
