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


# -- a float is "the same" up to a hair: one LayoutUnit (1/64 px) --------------------------------------------
def test_a_layout_unit_of_difference_is_within_the_default_tolerance():
    a, b = sc.parse(_svg('<rect width="155.28125"/>')), sc.parse(_svg('<rect width="155.296875"/>'))
    assert sc.compare(a, b) == []


def test_a_tenth_of_a_pixel_is_not():
    a, b = sc.parse(_svg('<rect width="155.28"/>')), sc.parse(_svg('<rect width="155.38"/>'))
    assert sc.compare(a, b)


# -- base64-encoded JSON (mermaid's data-points) is compared by its numbers, not as opaque text ------------------
def _b64(obj):
    import base64
    import json
    return base64.b64encode(json.dumps(obj).encode()).decode()


def test_numbers_inside_base64_json_are_compared_approximately():
    a = sc.parse(_svg(f'<path data-points="{_b64([{"x": 223.28125, "y": 134}, {"x": 248.28125, "y": 134}])}"/>'))
    b = sc.parse(_svg(f'<path data-points="{_b64([{"x": 223.296875, "y": 134}, {"x": 248.296875, "y": 134}])}"/>'))
    assert sc.compare(a, b) == []


def test_a_real_difference_inside_base64_json_is_reported():
    a = sc.parse(_svg(f'<path data-points="{_b64([{"x": 223.28125, "y": 134}])}"/>'))
    b = sc.parse(_svg(f'<path data-points="{_b64([{"x": 230.0, "y": 134}])}"/>'))
    assert sc.compare(a, b)


def test_base64_json_with_a_different_shape_or_text_is_reported():
    a = sc.parse(_svg(f'<path data-points="{_b64([{"x": 1}])}"/>'))
    assert sc.compare(a, sc.parse(_svg(f'<path data-points="{_b64([{"x": 1}, {"x": 2}])}"/>')))
    assert sc.compare(a, sc.parse(_svg(f'<path data-points="{_b64([{"z": 1}])}"/>')))
    assert sc.compare(sc.parse(_svg(f'<g data-n="{_b64({"name": "a"})}"/>')), sc.parse(_svg(f'<g data-n="{_b64({"name": "b"})}"/>')))


def test_an_ordinary_string_that_happens_to_look_like_base64_is_compared_as_text():
    assert sc.compare(sc.parse(_svg('<g id="abcdefgh"/>')), sc.parse(_svg('<g id="abcdefgi"/>')))


@pytest.mark.parametrize("not_base64", [
    "12345678", "1234567", "1234567890", "abcdefg", "ab+/cde",
    "MTIz-NA==",  # a valid encoding of 123 with a stray '-' in it: lenient decoders skip the '-' and accept it
    "MTIz NA==", "MTIzNA==x",
])
def test_a_string_that_is_not_well_formed_base64_is_never_decoded(not_base64):
    # "12345678" is valid JSON when read as text and decodes to bytes that are not; "1234567", "abcdefg" and
    # the like are not a multiple of four long. None of them may be treated as an encoded document.
    assert sc._decode_json(not_base64) is None


def test_base64_of_a_json_number_is_still_json():
    assert sc._decode_json(_b64(1234)) == 1234
    assert sc._decode_json(_b64("1234")) == "1234"


# -- nothing is ignored: only the floats get a tolerance ------------------------------------------------------
@pytest.mark.parametrize("a, b", [
    ("<g> </g>", "<g></g>"),                                  # whitespace-only text
    ("<g/><g/>", "<g/> <g/>"),                                # whitespace between elements
    ("<g>a</g>", "<g>a </g>"),                                # trailing space in text
    ("<g><!-- one --></g>", "<g><!-- two --></g>"),           # a comment's text
    ("<g><!-- c --></g>", "<g/>"),                            # a comment that is not there
    ("<g><?pi data?></g>", "<g/>"),                           # a processing instruction
    ("<g><![CDATA[a]]></g>", "<g>a</g>"),                     # CDATA is not the same node as text
])
def test_every_kind_of_node_counts(a, b):
    assert sc.compare(sc.parse(_svg(a)), sc.parse(_svg(b)))


def test_whitespace_inside_an_attribute_value_is_kept():
    # an XML parser normalizes a newline in an attribute to a space unless told not to
    a = sc.parse(_svg('<path d="M0 0\nL1 1"/>'))
    b = sc.parse(_svg('<path d="M0 0 L1 1"/>'))
    assert sc.compare(a, b)


def test_text_outside_the_root_element_counts():
    ok = '<svg xmlns="http://www.w3.org/2000/svg"/>'
    assert sc.compare(sc.parse(ok), sc.parse(ok)) == []
    assert sc.compare(sc.parse(ok), sc.parse('<?xml version="1.0"?>' + ok))
    assert sc.compare(sc.parse(ok), sc.parse(ok + "\n"))
    assert sc.compare(sc.parse(ok), sc.parse("<!-- hi -->" + ok))
    assert sc.compare(sc.parse(ok), sc.parse(ok + "<!-- bye -->"))


def test_numbers_in_comments_and_text_still_get_the_tolerance():
    assert sc.compare(sc.parse(_svg("<g><!-- w=10.000001 --></g>")), sc.parse(_svg("<g><!-- w=10 --></g>"))) == []


def test_an_attribute_on_either_side_only_is_reported_both_ways():
    a, b = sc.parse(_svg('<g id="x"/>')), sc.parse(_svg('<g id="x" class="y"/>'))
    assert any("only in the second" in d for d in sc.compare(a, b))
    assert any("only in the first" in d for d in sc.compare(b, a))
