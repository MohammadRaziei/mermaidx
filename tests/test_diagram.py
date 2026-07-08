"""Tests for the synchronous, mmdr-compatible API (mmdc.render() / Diagram)."""

from __future__ import annotations

import pytest

import mmdc

FLOWCHART = "flowchart LR\n    A[Start] --> B{OK?}\n    B -->|Yes| C[Done]"


def test_backends_includes_js():
    # 'js' is always available regardless of whether mmdr happens to be
    # installed in this environment.
    assert "js" in mmdc.backends()


def test_render_does_not_compute_anything_yet():
    """render() is now fully lazy: constructing a Diagram must not touch
    the engine at all -- not even to render SVG."""
    d = mmdc.render(FLOWCHART)
    assert isinstance(d, mmdc.Diagram)
    assert d._cache == {}  # nothing computed yet


def test_svg_computes_on_first_call():
    d = mmdc.render(FLOWCHART)
    svg = d.svg()
    assert svg.startswith("<svg")
    assert "Start" in svg and "Done" in svg
    assert d._cache  # now populated


def test_svg_is_cached_not_recomputed():
    d = mmdc.render(FLOWCHART)
    first = d.svg()
    assert d.svg() is first  # identical object, not just equal


def test_png_is_cached_per_arguments():
    d = mmdc.render(FLOWCHART)
    a = d.png(width=300)
    b = d.png(width=300)
    c = d.png(width=400)
    assert a is b               # same args -> cache hit, same object
    assert a != c or a is not c  # different args -> separate cache entry


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


# ── ascii ─────────────────────────────────────────────────────────────────

def test_ascii_method_exists_on_diagram():
    d = mmdc.render(FLOWCHART)
    art = d.ascii()
    assert isinstance(art, str) and art.strip()


def test_ascii_is_cached():
    d = mmdc.render(FLOWCHART)
    assert d.ascii() is d.ascii()


# ── save() ────────────────────────────────────────────────────────────────

def test_save_all_formats(tmp_path):
    d = mmdc.render(FLOWCHART)
    svg_path, png_path, pdf_path = tmp_path / "d.svg", tmp_path / "d.png", tmp_path / "d.pdf"
    d.save(str(svg_path))
    d.save(str(png_path))
    d.save(str(pdf_path))
    assert svg_path.read_text(encoding='utf-8').startswith("<svg")
    assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


def test_save_ascii_by_extension(tmp_path):
    out = tmp_path / "d.txt"
    mmdc.render(FLOWCHART).save(str(out))
    assert out.read_text().strip()


def test_save_format_override_ignores_extension(tmp_path):
    """save(..., format=...) forces the format regardless of the file extension."""
    out = tmp_path / "d.whatever"
    mmdc.render(FLOWCHART).save(str(out), format="svg")
    assert out.read_text().startswith("<svg")


def test_save_format_override_png_with_odd_extension(tmp_path):
    out = tmp_path / "d.backup"
    mmdc.render(FLOWCHART).save(str(out), format="png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_unknown_extension_raises(tmp_path):
    d = mmdc.render(FLOWCHART)
    with pytest.raises(ValueError):
        d.save(str(tmp_path / "d.bmp"))


def test_save_unknown_format_override_raises(tmp_path):
    d = mmdc.render(FLOWCHART)
    with pytest.raises(ValueError):
        d.save(str(tmp_path / "d.svg"), format="bmp")


# ── misc ──────────────────────────────────────────────────────────────────

def test_repr_svg_for_jupyter():
    d = mmdc.render(FLOWCHART)
    assert d._repr_svg_() == d.svg()


def test_repr():
    d = mmdc.render(FLOWCHART)
    assert "backend='js'" in repr(d)


def test_render_invalid_mermaid_raises_on_svg_not_on_render():
    """render() itself is lazy and never touches the engine, so the error
    only surfaces once something (here, .svg()) actually needs the result."""
    d = mmdc.render("this is not a valid mermaid diagram {{{")
    with pytest.raises(RuntimeError):
        d.svg()


def test_render_unknown_backend_without_mmdr_behaves_correctly():
    """If mmdr isn't installed, an mmdr-only backend must raise ImportError
    with install instructions. If mmdr *is* installed (e.g. a dev machine
    working on both packages), it should just work instead."""
    try:
        import mmdr  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match=r"mmdc\[rust\]"):
            mmdc.render(FLOWCHART, backend="merman")
    else:
        d = mmdc.render(FLOWCHART, backend="merman")
        assert d.svg().startswith("<svg") or d.svg().strip().startswith("<?xml")


def test_render_unknown_backend_name_raises_value_error():
    pytest.importorskip("mmdr")
    with pytest.raises(ValueError):
        mmdc.render(FLOWCHART, backend="not-a-real-backend")


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
