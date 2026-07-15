"""
Regression tests using a small corpus of real Mermaid source files, each
paired with a reference SVG rendered by mermaid.ink (the official/browser
rendering, via a real Chrome instance).

These caught real bugs this package's own hand-written test diagrams never
exercised: stadium-shaped nodes and stateDiagram start/end circles crashed
outright (missing `RegExp.$1` legacy static properties -- QuickJS-ng doesn't
implement them, but a roughjs-derived path parser bundled in mermaid.js
relies on them; and missing `Element.children`/`.matches()` in the DOM
shim), and mindmap needed a Canvas 2D shim, several missing DOM methods,
and an async-timer fix (see dom_shim.js/engine.py) before it would render
at all.

Comparison is structural (label words + aspect ratio) for the reference-svg
checks, but several checks below render to real pixels and inspect them
directly -- some bugs (CSS-cascade-only positioning issues) are invisible
in the SVG's own attribute values and only show up once something actually
paints the markup.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mermaidx

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_NAMES = sorted(p.stem for p in SAMPLES_DIR.glob("*.mmd"))


def _svg_texts(svg_str: str) -> list[str]:
    """All human-readable label text in an SVG -- plain <text>/<tspan> or
    HTML wrapped inside a <foreignObject> (<div>/<span>/<p>). Skips
    <style>/<script>, which carry CSS/JS text, not labels."""
    root = ET.fromstring(svg_str)
    skip = {"style", "script"}
    return sorted(
        el.text.strip()
        for el in root.iter()
        if el.tag.split("}")[-1] not in skip and el.text and el.text.strip()
    )


def _svg_aspect_ratio(svg_str: str) -> float:
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_str)
    assert m, "no viewBox found"
    _, _, w, h = (float(x) for x in m.group(1).split())
    return w / h


# Historically mindmap needed a Canvas 2D shim (cytoscape's internal
# layout/renderer touches <canvas> during init even for a one-shot
# headless render). That's since been added -- see dom_shim.js's
# __makeCanvas2dContext and the DOM methods around it -- so this set is
# empty for now. Kept as a named place to list future gaps rather than
# something disappearing silently into a plain skip.
KNOWN_UNSUPPORTED: set[str] = set()


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_sample_renders_without_error(name):
    if name in KNOWN_UNSUPPORTED:
        pytest.xfail(f"{name}: needs a Canvas 2D context shim (not yet implemented)")
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    d = mermaidx.render(source)
    assert d.svg().startswith("<svg")


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_labels_match_reference(name):
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    reference_svg = (SAMPLES_DIR / f"{name}.svg").read_text(encoding="utf-8")

    ours = mermaidx.render(source).svg()

    reference_words = sorted(" ".join(_svg_texts(reference_svg)).split())
    our_words = sorted(" ".join(_svg_texts(ours)).split())
    assert our_words == reference_words, (
        f"label text mismatch for {name!r}:\n"
        f"  reference: {reference_words}\n"
        f"  ours:      {our_words}"
    )


# Same rationale as test_online_comparison.py's ASPECT_DIAGRAMS split: aspect
# ratio is only a meaningful cross-check when node labels are short enough
# that real CSS word-wrap (mermaid.ink, htmlLabels:true) vs this package's
# htmlLabels:false doesn't change node proportions much either way. For
# flowchart/ER diagrams with substantial label text, that wrapping decision
# measurably changes the whole diagram's shape -- a known, accepted
# trade-off (see engine.py), not something to chase with an ever-looser
# tolerance. The label-content check above still applies to all of them.
ASPECT_RATIO_MEANINGFUL_FOR = {"03_simple_sequence", "04_simple_state", "06_complex_sequence"}


@pytest.mark.parametrize("name", sorted(ASPECT_RATIO_MEANINGFUL_FOR))
def test_sample_aspect_ratio_close_to_reference(name):
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    reference_svg = (SAMPLES_DIR / f"{name}.svg").read_text(encoding="utf-8")

    ours = mermaidx.render(source).svg()

    reference_ratio = _svg_aspect_ratio(reference_svg)
    our_ratio = _svg_aspect_ratio(ours)
    rel_diff = abs(our_ratio - reference_ratio) / reference_ratio
    assert rel_diff < 0.35, (
        f"aspect ratio for {name!r} differs too much: "
        f"ours={our_ratio:.3f} reference={reference_ratio:.3f} (delta={rel_diff:.0%})"
    )


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_png_and_pdf_also_work(name):
    """The SVG comparisons above are the interesting part; this just makes
    sure the rest of the pipeline (resvg, the PDF writer) doesn't choke on
    any of these samples either."""
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    d = mermaidx.render(source)
    assert d.png()[:8] == b"\x89PNG\r\n\x1a\n"
    assert d.pdf()[:5] == b"%PDF-"


# --- Geometry/framing checks -------------------------------------------
#
# Everything above is structural (label words, viewBox aspect ratio) and,
# as it turned out, completely blind to a whole class of real bugs: a
# node's shape painting over its own label (z-order), getBBox() silently
# returning zero for a shape so the layout engine placed nodes overlapping
# each other, and diagram content actually clipped by too-tight a viewBox.
# All of those rendered a structurally-valid SVG with the right words in
# it and passed every test above anyway. These render to actual pixels and
# check the geometry a person would notice at a glance.

# Small opaque margin so the check isn't defeated by 1px antialiasing
# fuzz at the very edge of a shape.
_EDGE_TOUCH_TOLERANCE_PX = 2


def _nonwhite_mask(rgba):
    """True where a pixel is neither white nor fully transparent."""
    import numpy as np

    opaque = rgba[:, :, 3] > 0
    nonwhite = np.any(rgba[:, :, :3] != 255, axis=2)
    return opaque & nonwhite


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_content_not_clipped_by_canvas(name):
    """Rendered content must not touch the PNG's own edge. If it does, the
    viewBox mermaid computed was too tight and part of the diagram (a
    label, an edge, a node) is being cut off -- exactly what happened when
    getBBox() ignored child transforms / didn't understand <polygon>."""
    pytest.importorskip("numpy")
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    arr = mermaidx.render(source).numpy()
    mask = _nonwhite_mask(arr)
    rows = mask.any(axis=1)
    cols = mask.any(axis=0)
    assert rows.any() and cols.any(), f"{name}: rendered PNG is blank"
    y0, y1 = rows.argmax(), len(rows) - 1 - rows[::-1].argmax()
    x0, x1 = cols.argmax(), len(cols) - 1 - cols[::-1].argmax()
    h, w = mask.shape
    assert y0 >= _EDGE_TOUCH_TOLERANCE_PX, f"{name}: content clipped at top edge"
    assert x0 >= _EDGE_TOUCH_TOLERANCE_PX, f"{name}: content clipped at left edge"
    assert y1 <= h - 1 - _EDGE_TOUCH_TOLERANCE_PX, f"{name}: content clipped at bottom edge"
    assert x1 <= w - 1 - _EDGE_TOUCH_TOLERANCE_PX, f"{name}: content clipped at right edge"


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_node_shapes_drawn_before_labels(name):
    """A node's own shape (rect/polygon/circle/...) must come before its
    label in document order, so the label paints on top and stays
    readable -- not the other way around, which silently hides every
    node's text behind its own opaque fill (the very first bug in this
    file's history) while every word-content test above kept passing."""
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    svg = mermaidx.render(source).svg()
    root = ET.fromstring(svg)
    ns_strip = lambda tag: tag.split("}")[-1]
    shape_tags = {"rect", "polygon", "circle", "ellipse", "path"}
    offenders = []
    for node in root.iter():
        if "node" not in (node.get("class") or "").split():
            continue
        children = list(node)
        label_idx = next(
            (i for i, c in enumerate(children) if "label" in (c.get("class") or "").split()),
            None,
        )
        if label_idx is None:
            continue
        shape_idx = next(
            (i for i, c in enumerate(children) if ns_strip(c.tag) in shape_tags),
            None,
        )
        if shape_idx is not None and shape_idx > label_idx:
            offenders.append(node.get("id"))
    assert not offenders, f"{name}: node shape painted after (on top of) its label: {offenders}"


def _translate_of(el) -> tuple[float, float]:
    m = re.search(r"translate\(\s*(-?[\d.]+)(?:[,\s]+(-?[\d.]+))?\s*\)", el.get("transform") or "")
    if not m:
        return 0.0, 0.0
    return float(m.group(1)), float(m.group(2) or 0)


def _shape_local_bbox(el, ns_strip):
    """Local (pre-transform) bbox of a shape element, reusing the same
    parser already validated for mermaidx's own bbox computation."""
    from mermaidx.engine import _path_bbox

    tag = ns_strip(el.tag)
    if tag == "rect":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        return x, y, x + w, y + h
    if tag == "circle":
        cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0))
        return cx - r, cy - r, cx + r, cy + r
    if tag == "ellipse":
        cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
        rx, ry = float(el.get("rx", 0)), float(el.get("ry", 0))
        return cx - rx, cy - ry, cx + rx, cy + ry
    if tag == "polygon" or tag == "polyline":
        nums = [float(n) for n in re.split(r"[\s,]+", (el.get("points") or "").strip()) if n]
        xs, ys = nums[0::2], nums[1::2]
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)
    if tag == "path":
        b = _path_bbox(el.get("d") or "")
        if b["width"] == 0 and b["height"] == 0:
            return None
        return b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
    return None


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_labels_inside_their_own_shape(name):
    """A node's label must sit within (a padded version of) that node's
    own shape -- not off to the side of it. Shapes with a manually
    computed label transform (the cylinder is the one that actually hit
    this) depend on getBBox()/text-anchor being resolved correctly; get
    either wrong and the label drifts outside the shape it's meant to
    label while everything still parses as valid, word-complete SVG."""
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    svg = mermaidx.render(source).svg()
    root = ET.fromstring(svg)
    ns_strip = lambda tag: tag.split("}")[-1]
    shape_tags = {"rect", "polygon", "circle", "ellipse", "path"}

    offenders = []
    for node in root.iter():
        if "node" not in (node.get("class") or "").split():
            continue
        children = list(node)
        shape = next((c for c in children if ns_strip(c.tag) in shape_tags), None)
        label = next(
            (c for c in children if "label" in (c.get("class") or "").split()), None
        )
        if shape is None or label is None:
            continue
        bbox = _shape_local_bbox(shape, ns_strip)
        if bbox is None:
            continue
        sx, sy = _translate_of(shape)
        x0, y0, x1, y1 = bbox[0] + sx, bbox[1] + sy, bbox[2] + sx, bbox[3] + sy
        lx, ly = _translate_of(label)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # Generous relative to shape size, but centered on the shape's
        # actual center -- not just "somewhere inside the (padded) bbox",
        # which a label shifted most of the way to one side can still
        # satisfy for a wide shape like a cylinder.
        tol_x = 0.35 * max(x1 - x0, 1)
        tol_y = 0.35 * max(y1 - y0, 1)
        if abs(lx - cx) > tol_x or abs(ly - cy) > tol_y:
            offenders.append((node.get("id"), (lx, ly), "center", (cx, cy)))
    assert not offenders, f"{name}: label positioned outside its own node shape: {offenders}"


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_label_pixels_centered_in_shape(name):
    """Pixel-level check that a label's ink is actually centered within its
    own node shape once painted -- not just that some SVG attribute value
    looks plausible. The XML-attribute version of this check
    (test_sample_labels_inside_their_own_shape) is blind to bugs that live
    purely in CSS resolution at paint time (confirmed directly: a broken
    and a fixed render of the mindmap sample differ in exactly one
    injected stylesheet rule and are byte-identical everywhere else,
    including every transform attribute), so this renders to real pixels
    instead of trusting the markup."""
    pytest.importorskip("numpy")
    import numpy as np

    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    d = mermaidx.render(source)
    svg = d.svg()
    arr = d.numpy()
    h, w = arr.shape[:2]

    vb_m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg)
    assert vb_m, f"{name}: no viewBox"
    vx0, vy0, vw, vh = (float(x) for x in vb_m.group(1).split())
    sx, sy = w / vw, h / vh  # user-units -> pixels

    root = ET.fromstring(svg)
    ns_strip = lambda tag: tag.split("}")[-1]
    shape_tags = {"rect", "polygon", "circle", "ellipse", "path"}

    offenders = []
    checked = 0
    for node in root.iter():
        if "node" not in (node.get("class") or "").split():
            continue
        children = list(node)
        shape = next((c for c in children if ns_strip(c.tag) in shape_tags), None)
        label = next((c for c in children if "label" in (c.get("class") or "").split()), None)
        if shape is None or label is None or not (label.itertext() and "".join(label.itertext()).strip()):
            continue
        bbox = _shape_local_bbox(shape, ns_strip)
        if bbox is None or bbox[2] - bbox[0] < 4 or bbox[3] - bbox[1] < 4:
            continue  # too small to meaningfully check (icon glyphs etc.)
        nx, ny = _translate_of(node)
        shx, shy = _translate_of(shape)
        x0 = (nx + shx + bbox[0] - vx0) * sx
        x1 = (nx + shx + bbox[2] - vx0) * sx
        y0 = (ny + shy + bbox[1] - vy0) * sy
        y1 = (ny + shy + bbox[3] - vy0) * sy
        px0, px1 = max(0, int(x0)), min(w, int(x1))
        py0, py1 = max(0, int(y0)), min(h, int(y1))
        if px1 - px0 < 6 or py1 - py0 < 6:
            continue
        crop = arr[py0:py1, px0:px1, :3].astype(int)
        # The shape's own fill is whatever color covers the most pixels;
        # text pixels are the ones that differ meaningfully from it.
        flat = crop.reshape(-1, 3)
        colors, counts = np.unique(flat, axis=0, return_counts=True)
        fill = colors[counts.argmax()]
        dist = np.abs(flat.astype(int) - fill.astype(int)).sum(axis=1)
        text_mask = dist > 60
        if text_mask.sum() < 5:
            continue  # no discernible text ink found (nothing to check)
        checked += 1
        ys, xs = np.divmod(np.where(text_mask)[0], crop.shape[1])
        cx_ink, cy_ink = xs.mean(), ys.mean()
        cx_box, cy_box = crop.shape[1] / 2, crop.shape[0] / 2
        tol_x, tol_y = 0.12 * crop.shape[1], 0.25 * crop.shape[0]
        if abs(cx_ink - cx_box) > tol_x or abs(cy_ink - cy_box) > tol_y:
            offenders.append((node.get("id"), (round(cx_ink), round(cy_ink)), (round(cx_box), round(cy_box))))
    if checked == 0:
        pytest.skip(f"{name}: no node matched this check's shape+label assumptions")
    assert not offenders, f"{name}: label ink off-center within its shape (ink_centroid vs box_center): {offenders}"


@pytest.mark.parametrize("name", [n for n in SAMPLE_NAMES if n not in KNOWN_UNSUPPORTED])
def test_sample_sibling_labels_not_stacked(name):
    """Sibling label groups with different text (e.g. an ER-diagram row's
    type/name/keys/comment columns) must not share the exact same
    transform -- that means whatever was supposed to shift them apart
    (mermaid's own "g:not(:first-child)" column-repositioning selector,
    in the ER case) silently never ran, and every column in the row
    prints on top of the others."""
    source = (SAMPLES_DIR / f"{name}.mmd").read_text(encoding="utf-8")
    svg = mermaidx.render(source).svg()
    root = ET.fromstring(svg)
    ns_strip = lambda tag: tag.split("}")[-1]

    def label_text(g):
        return "".join(t.strip() for t in g.itertext() if t.strip())

    offenders = []
    for parent in root.iter():
        seen = {}
        for child in parent:
            if ns_strip(child.tag) != "g" or "label" not in (child.get("class") or "").split():
                continue
            text = label_text(child)
            transform = child.get("transform") or ""
            if not text:
                continue
            key = transform
            if key in seen and seen[key] != text:
                offenders.append((seen[key], text, transform))
            else:
                seen[key] = text
    assert not offenders, f"{name}: sibling labels sharing one position: {offenders}"
