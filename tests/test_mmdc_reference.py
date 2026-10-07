"""mermaidx's SVG vs the SVG real mermaid-cli (mmdc) produces for the same diagram.

The references next to each sample in tests/samples/ come from mmdc running mermaid.js in Chromium with DejaVu Sans
(see tests/samples/README.md for the exact recipe). Elements, attributes and the <style> rules
are compared one by one; the only things normalised away are what mmdc itself adds on top of
mermaid.js's output: the root `background-color` (its -b option) and the 3-decimal rounding of the
root `max-width` (it re-writes the style through the CSSOM), plus the per-render svg id.
"""
import glob
import os
import re
import xml.etree.ElementTree as ET

import pytest

import mermaidx

HERE = os.path.dirname(__file__)
SAMPLES = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "samples", "*.mmd")))

# Samples whose SVG still differs from mmdc's, each with what is known about why. These are strict
# xfails: the day one of them starts matching, the suite fails and the entry has to be removed here.
KNOWN_DIFFERENT = {
    "21_xychart": "bar x/width come back from Chrome as single-precision values (91.34687690734863); "
                  "where that float32 round-trip happens is not found yet",
    "22_sankey": "viewBox y differs by one float32 ulp; most likely Chrome (Skia) computes the bbox of the "
                 "bezier link paths in single precision, mermaidx does it in double and rounds at the end",
    "24_c4_context": "Chrome writes the <image> href as xlink:href (the shim drops the namespace) and the "
                     "shapes are placed differently (699,464 vs 200,700); not investigated further",
    "30_treemap": "the ref keeps the raw style attribute ('font-size: 38px;fill:#ffffff;') where mermaidx "
                  "re-serializes it, and the viewBox differs; not investigated further",
    "32_ishikawa": "text sizes and positions differ (viewBox width 693 vs 501); cause not found yet",
    "39_mindmap_shapes": "node/edge coordinates differ (cytoscape layout inputs); cause not found yet",
    "42_flowchart_markdown_labels": "inline <strong>/<em> in a foreignObject label: novasvg's ForeignObjectSimple "
                                    "strips tags to plain text, so bold runs are measured regular "
                                    "('Group one' 83.57 vs Chrome 89.72 = bold('Group') + regular(' one'))",
}

_NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _local(tag):
    return tag.split("}")[-1]


def _norm(value, svg_id):
    value = value.replace(svg_id, "ID")
    value = re.sub(r"\s*background-color:\s*(?:white|transparent);?", "", value).strip()
    return re.sub(r"max-width: ([\d.]+)px", lambda m: "max-width: %spx" % round(float(m.group(1)), 3), value)


def _rules(css, svg_id):
    css = re.sub(r"\s+", " ", css.replace(svg_id, "ID"))
    out, depth, cur = [], 0, ""
    for ch in css:
        cur += ch
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append(cur.strip())
                cur = ""
    return out


def _svg_id(svg):
    return re.search(r'<svg[^>]*\bid="([^"]+)"', svg).group(1)


def _diff(ours, ref):
    """-> (structure_ok, number_of_differing_attribute_values, css_rules_identical)"""
    io, ir = _svg_id(ours), _svg_id(ref)
    a = [e for e in ET.fromstring(ours).iter() if _local(e.tag) != "style"]
    b = [e for e in ET.fromstring(ref).iter() if _local(e.tag) != "style"]
    # a diagram may have no <style> at all (wardley); then both must have none
    def css(s, i):
        m = re.search(r"<style>(.*?)</style>", s, re.S)
        return None if m is None else _rules(m.group(1), i)
    css_same = css(ours, io) == css(ref, ir)
    if [_local(e.tag) for e in a] != [_local(e.tag) for e in b]:
        return False, -1, css_same
    bad = 0
    for x, y in zip(a, b):
        # the text inside an element is part of the output too (a label that came out empty is a diff)
        for own, other in ((x.text, y.text), (x.tail, y.tail)):
            if (own or "").replace(io, "ID") != (other or "").replace(ir, "ID"):
                bad += 1
        for k in set(x.attrib) | set(y.attrib):
            if k == "id":
                continue
            if _norm(x.get(k, "<none>"), io) != _norm(y.get(k, "<none>"), ir):
                bad += 1
    return True, bad, css_same


@pytest.mark.parametrize(
    "name",
    [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN_DIFFERENT[n])) if n in KNOWN_DIFFERENT else n
     for n in SAMPLES],
)
def test_svg_matches_mmdc(name):
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    ref = open(os.path.join(HERE, "samples", name + ".svg"), encoding="utf-8").read()
    ours = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()

    same_structure, differing, css_same = _diff(ours, ref)
    assert same_structure, f"{name}: element sequence differs from mmdc's"
    assert css_same, f"{name}: <style> rules differ from mmdc's"
    assert differing == 0, f"{name}: {differing} attribute value(s) differ from mmdc"
