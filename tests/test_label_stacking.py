"""The 'sibling labels must not share a position' check, on hand-made markup.

Mermaid positions a label either with a transform on its `<g class="label">` (flowchart nodes, ER
rows) or with a transform on the `<text>` inside it, leaving the group itself untransformed
(quadrant-chart axis labels). Both place the labels apart. What is wrong is labels that end up at the
same place: the layout step that should have moved them never ran.
"""
import xml.etree.ElementTree as ET

from test_samples import _stacked_sibling_labels

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><g>{}</g></svg>'


def offenders(children):
    return _stacked_sibling_labels(ET.fromstring(SVG.format(children)))


def test_two_different_labels_on_the_same_group_transform_are_stacked():
    # an ER row whose column-shifting rule never ran: every column prints on the same spot
    assert offenders(
        '<g class="label" transform="translate(10,5)"><text>type</text></g>'
        '<g class="label" transform="translate(10,5)"><text>name</text></g>'
    )


def test_labels_placed_by_their_own_text_transform_are_not_stacked():
    # quadrant chart axis labels: untransformed groups, each text carries its own transform
    assert not offenders(
        '<g class="label"><text transform="translate(147, 479)">Low Reach</text></g>'
        '<g class="label"><text transform="translate(379, 479)">High Reach</text></g>'
    )


def test_labels_whose_text_sits_at_the_same_spot_are_still_stacked():
    assert offenders(
        '<g class="label"><text transform="translate(5, 5)">one</text></g>'
        '<g class="label"><text transform="translate(5, 5)">two</text></g>'
    )


def test_labels_with_the_same_text_are_not_a_problem():
    assert not offenders(
        '<g class="label" transform="translate(1,1)"><text>same</text></g>'
        '<g class="label" transform="translate(1,1)"><text>same</text></g>'
    )
