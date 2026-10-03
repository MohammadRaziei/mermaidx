"""mermaidx's SVG vs the SVG real mermaid-cli (mmdc) produces for the same diagram.

The references in tests/samples/mmdc/ come from mmdc running mermaid.js in Chromium with DejaVu Sans
(see tests/samples/mmdc/README.md for the exact recipe). Elements, attributes and the <style> rules
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
    css = lambda s, i: _rules(re.search(r"<style>(.*?)</style>", s, re.S).group(1), i)
    css_same = css(ours, io) == css(ref, ir)
    if [_local(e.tag) for e in a] != [_local(e.tag) for e in b]:
        return False, -1, css_same
    bad = 0
    for x, y in zip(a, b):
        for k in set(x.attrib) | set(y.attrib):
            if k == "id":
                continue
            if _norm(x.get(k, "<none>"), io) != _norm(y.get(k, "<none>"), ir):
                bad += 1
    return True, bad, css_same


@pytest.mark.parametrize("name", SAMPLES)
def test_svg_matches_mmdc(name):
    src = open(os.path.join(HERE, "samples", name + ".mmd"), encoding="utf-8").read()
    ref = open(os.path.join(HERE, "samples", "mmdc", name + ".svg"), encoding="utf-8").read()
    ours = mermaidx.render(src, config={"handDrawnSeed": 1}).svg()

    same_structure, differing, css_same = _diff(ours, ref)
    assert same_structure, f"{name}: element sequence differs from mmdc's"
    assert css_same, f"{name}: <style> rules differ from mmdc's"
    assert differing == 0, f"{name}: {differing} attribute value(s) differ from mmdc"
