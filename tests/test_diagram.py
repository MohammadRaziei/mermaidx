"""Tests for the synchronous, mmdr-compatible API (mmdc.render() / Diagram)."""

from __future__ import annotations

import pytest

import mmdc

FLOWCHART = "flowchart LR\n    A[Start] --> B{OK?}\n    B -->|Yes| C[Done]"


def test_backends_without_mmdr():
    # In this test environment mmdr is not installed.
    assert mmdc.backends() == ["js"]


def test_render_returns_diagram_with_svg_already_computed():
    d = mmdc.render(FLOWCHART)
    assert isinstance(d, mmdc.Diagram)
    # svg() must not need a separate render step -- it's already done.
    assert d._svg is not None
    svg = d.svg()
    assert svg.startswith("<svg")
    assert "Start" in svg and "Done" in svg


def test_svg_is_cached_not_recomputed():
    d = mmdc.render(FLOWCHART)
    first = d.svg()
    assert d.svg() is first  # identical object, not just equal


def test_png():
    d = mmdc.render(FLOWCHART)
    png = d.png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_with_background_and_width():
    """resvg (like most SVG rasterizers) preserves aspect ratio when a
    single dimension is given -- it doesn't stretch to arbitrary w+h."""
    png = mmdc.render(FLOWCHART).png(width=400, background="#ffffff")
    from mmdc.png_decode import decode_png
    decoded = decode_png(png)
    assert decoded.width == 400


def test_raw():
    d = mmdc.render(FLOWCHART)
    raw, w, h = d.raw()
    assert len(raw) == w * h * 4


def test_numpy():
    np = pytest.importorskip("numpy")
    d = mmdc.render(FLOWCHART)
    arr = d.numpy()
    assert arr.dtype == np.uint8
    assert arr.ndim == 3 and arr.shape[2] == 4


def test_pdf_fully_supported_unlike_mmdr():
    """mmdr's own Diagram.pdf() raises NotImplementedError; ours works."""
    d = mmdc.render(FLOWCHART)
    pdf = d.pdf()
    assert pdf[:5] == b"%PDF-"


def test_save_all_formats(tmp_path):
    d = mmdc.render(FLOWCHART)
    svg_path, png_path, pdf_path = tmp_path / "d.svg", tmp_path / "d.png", tmp_path / "d.pdf"
    d.save(str(svg_path))
    d.save(str(png_path))
    d.save(str(pdf_path))
    assert svg_path.read_text().startswith("<svg")
    assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


def test_save_unknown_extension_raises(tmp_path):
    d = mmdc.render(FLOWCHART)
    with pytest.raises(ValueError):
        d.save(str(tmp_path / "d.bmp"))


def test_repr_svg_for_jupyter():
    d = mmdc.render(FLOWCHART)
    assert d._repr_svg_() == d.svg()


def test_repr():
    d = mmdc.render(FLOWCHART)
    assert "backend='js'" in repr(d)


def test_render_invalid_mermaid_raises():
    with pytest.raises(RuntimeError):
        mmdc.render("this is not a valid mermaid diagram {{{")


def test_render_unknown_backend_without_mmdr_raises_import_error():
    with pytest.raises(ImportError):
        mmdc.render(FLOWCHART, backend="merman")


def test_render_js_backend_explicit():
    d = mmdc.render(FLOWCHART, backend="js")
    assert isinstance(d, mmdc.Diagram)


def test_svg_to_png_standalone_utility():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">' \
          '<rect width="40" height="40" fill="blue"/></svg>'
    png = mmdc.svg_to_png(svg)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_to_raw_standalone_utility():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">' \
          '<rect width="40" height="40" fill="blue"/></svg>'
    raw, w, h = mmdc.svg_to_raw(svg)
    assert (w, h) == (40, 40)
    assert len(raw) == 40 * 40 * 4
