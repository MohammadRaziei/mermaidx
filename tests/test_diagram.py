"""Tests for the synchronous, mmdr-compatible API (mermaidx.render() / Diagram)."""

from __future__ import annotations

import pytest

import mermaidx

FLOWCHART = "flowchart LR\n    A[Start] --> B{OK?}\n    B -->|Yes| C[Done]"


def test_backends_includes_quickjs():
    # 'quickjs' is always available regardless of whether mmdr happens to be
    # installed in this environment.
    assert "quickjs" in mermaidx.backends()


def test_backends_v8_reflects_py_mini_racer_availability(monkeypatch):
    """https://github.com/MohammadRaziei/mermaidx/issues/28

    backends() used to check `import mermaidx.engines.v8_engine` for v8
    availability, but that module always imports fine -- it deliberately
    defers `from py_mini_racer import MiniRacer` to inside
    _build_context(), since that's meant to run in a multiprocessing
    child process. So 'v8' showed up in backends() even when mini-racer
    was never installed. The check has to import py_mini_racer itself.
    """
    import builtins
    import sys

    real_import = builtins.__import__

    def fake_import_missing(name, *args, **kwargs):
        if name == "py_mini_racer" or name.startswith("py_mini_racer."):
            raise ImportError("simulated: mini-racer not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "py_mini_racer", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import_missing)
    assert "v8" not in mermaidx.backends()

    monkeypatch.setattr(builtins, "__import__", real_import)
    monkeypatch.setitem(sys.modules, "py_mini_racer", type(sys)("py_mini_racer"))
    assert "v8" in mermaidx.backends()


def test_render_does_not_compute_anything_yet():
    """render() is now fully lazy: constructing a Diagram must not touch
    the engine at all -- not even to render SVG."""
    d = mermaidx.render(FLOWCHART)
    assert isinstance(d, mermaidx.Diagram)
    assert d._cache == {}  # nothing computed yet


def test_svg_computes_on_first_call():
    d = mermaidx.render(FLOWCHART)
    svg = d.svg()
    assert svg.startswith("<svg")
    assert "Start" in svg and "Done" in svg
    assert d._cache  # now populated


def test_svg_is_cached_not_recomputed():
    d = mermaidx.render(FLOWCHART)
    first = d.svg()
    assert d.svg() is first  # identical object, not just equal


def test_png_is_cached_per_arguments():
    d = mermaidx.render(FLOWCHART)
    a = d.png(width=300)
    b = d.png(width=300)
    c = d.png(width=400)
    assert a is b               # same args -> cache hit, same object
    assert a != c or a is not c  # different args -> separate cache entry


def test_png():
    d = mermaidx.render(FLOWCHART)
    png = d.png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_with_background_and_width():
    """resvg (like most SVG rasterizers) preserves aspect ratio when a
    single dimension is given -- it doesn't stretch to arbitrary w+h."""
    png = mermaidx.render(FLOWCHART).png(width=400, background="#ffffff")
    from mermaidx.png_decode import decode_png
    decoded = decode_png(png)
    assert decoded.width == 400


def test_raw():
    d = mermaidx.render(FLOWCHART)
    raw, w, h = d.raw()
    assert len(raw) == w * h * 4


def test_numpy():
    np = pytest.importorskip("numpy")
    d = mermaidx.render(FLOWCHART)
    arr = d.numpy()
    assert arr.dtype == np.uint8
    assert arr.ndim == 3 and arr.shape[2] == 4


def test_pdf_fully_supported_unlike_mmdr():
    """mmdr's own Diagram.pdf() raises NotImplementedError; ours works."""
    d = mermaidx.render(FLOWCHART)
    pdf = d.pdf()
    assert pdf[:5] == b"%PDF-"


# ── ascii ─────────────────────────────────────────────────────────────────

def test_ascii_method_exists_on_diagram():
    d = mermaidx.render(FLOWCHART)
    art = d.ascii()
    assert isinstance(art, str) and art.strip()


def test_ascii_is_cached():
    d = mermaidx.render(FLOWCHART)
    assert d.ascii() is d.ascii()


# ── save() ────────────────────────────────────────────────────────────────

def test_save_all_formats(tmp_path):
    d = mermaidx.render(FLOWCHART)
    svg_path, png_path, pdf_path = tmp_path / "d.svg", tmp_path / "d.png", tmp_path / "d.pdf"
    d.save(str(svg_path))
    d.save(str(png_path))
    d.save(str(pdf_path))
    assert svg_path.read_text(encoding="utf-8").startswith("<svg")
    assert png_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert pdf_path.read_bytes()[:5] == b"%PDF-"


def test_save_ascii_by_extension(tmp_path):
    out = tmp_path / "d.txt"
    mermaidx.render(FLOWCHART).save(str(out))
    assert out.read_text(encoding="utf-8").strip()


def test_save_format_override_ignores_extension(tmp_path):
    """save(..., format=...) forces the format regardless of the file extension."""
    out = tmp_path / "d.whatever"
    mermaidx.render(FLOWCHART).save(str(out), format="svg")
    assert out.read_text(encoding="utf-8").startswith("<svg")


def test_save_format_override_png_with_odd_extension(tmp_path):
    out = tmp_path / "d.backup"
    mermaidx.render(FLOWCHART).save(str(out), format="png")
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_unknown_extension_raises(tmp_path):
    d = mermaidx.render(FLOWCHART)
    with pytest.raises(ValueError):
        d.save(str(tmp_path / "d.bmp"))


def test_save_unknown_format_override_raises(tmp_path):
    d = mermaidx.render(FLOWCHART)
    with pytest.raises(ValueError):
        d.save(str(tmp_path / "d.svg"), format="bmp")


# ── misc ──────────────────────────────────────────────────────────────────

def test_repr_svg_for_jupyter():
    d = mermaidx.render(FLOWCHART)
    assert d._repr_svg_() == d.svg()


def test_show_does_not_raise():
    pytest.importorskip("IPython")
    d = mermaidx.render(FLOWCHART)
    d.show()  # just needs to not raise; actual display is a no-op outside a kernel


def test_show_without_ipython_raises_clear_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "IPython", None)
    monkeypatch.setitem(sys.modules, "IPython.display", None)
    d = mermaidx.render(FLOWCHART)
    with pytest.raises(ImportError, match="pip install ipython"):
        d.show()


def test_show_is_backend_agnostic():
    """show()/_repr_svg_() live entirely on DiagramBase and just display
    self.svg() -- they don't care which backend produced it."""
    pytest.importorskip("IPython")
    d = mermaidx.render(FLOWCHART, backend="quickjs")
    d.show()  # exercises the same DiagramBase.show() a DiagramRust instance would use


def test_repr():
    d = mermaidx.render(FLOWCHART)
    assert "backend='quickjs'" in repr(d)


def test_render_invalid_mermaid_raises_on_svg_not_on_render():
    """render() itself is lazy and never touches the engine, so the error
    only surfaces once something (here, .svg()) actually needs the result."""
    d = mermaidx.render("this is not a valid mermaid diagram {{{")
    with pytest.raises(RuntimeError):
        d.svg()


def test_render_unknown_backend_without_mmdr_behaves_correctly():
    """If mmdr isn't installed, an mmdr-only backend must raise ImportError
    with install instructions. If mmdr *is* installed (e.g. a dev machine
    working on both packages), it should just work instead."""
    try:
        import mmdr  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match=r"mermaidx\[rust\]"):
            mermaidx.render(FLOWCHART, backend="merman")
    else:
        d = mermaidx.render(FLOWCHART, backend="merman")
        assert d.svg().startswith("<svg") or d.svg().strip().startswith("<?xml")


def test_mmdr_backend_gets_pdf_support_it_doesnt_natively_have():
    """The whole point of DiagramBase: mmdr's own Diagram.pdf() raises
    NotImplementedError, but ours reuses our resvg + PDF writer on top of
    mmdr's svg() -- so PDF export works for mmdr backends too."""
    pytest.importorskip("mmdr")
    d = mermaidx.render(FLOWCHART, backend="merman")
    assert d.pdf()[:5] == b"%PDF-"


def test_render_unknown_backend_name_raises_value_error():
    pytest.importorskip("mmdr")
    with pytest.raises(ValueError):
        mermaidx.render(FLOWCHART, backend="not-a-real-backend")


def test_render_quickjs_backend_explicit():
    d = mermaidx.render(FLOWCHART, backend="quickjs")
    assert isinstance(d, mermaidx.Diagram)


def test_svg_to_png_standalone_utility():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">' \
          '<rect width="40" height="40" fill="blue"/></svg>'
    png = mermaidx.svg_to_png(svg)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_to_raw_standalone_utility():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">' \
          '<rect width="40" height="40" fill="blue"/></svg>'
    raw, w, h = mermaidx.svg_to_raw(svg)
    assert (w, h) == (40, 40)
    assert len(raw) == 40 * 40 * 4


def test_gantt_diagram_renders():
    """Regression: mermaid's gantt renderer read `.parentElement.offsetWidth`
    off the rendered container, but the DOM shim's Node class had no
    parentElement getter at all, so this raised
    'cannot read property offsetWidth of undefined' (issue #13)."""
    svg = mermaidx.render(
        "gantt\n"
        "    section Section\n"
        "    Completed :done, des1, 2014-01-06, 2014-01-08\n"
        "    Active    :active, des2, 2014-01-07, 3d\n"
    ).svg()
    assert svg.startswith("<svg")
    assert 'aria-roledescription="gantt"' in svg


def test_pie_diagram_renders():
    """Regression: mermaid's default-config cloning calls the real
    structuredClone(), which QuickJS doesn't provide at all, so this raised
    'ReferenceError: structuredClone is not defined' (issue #15)."""
    svg = mermaidx.render('pie\n"Dogs" : 386\n"Cats" : 85.9\n"Rats" : 15\n').svg()
    assert svg.startswith("<svg")
    assert 'aria-roledescription="pie"' in svg


def test_c4_diagram_renders():
    """Regression: mermaid's C4 layout reads `screen.availWidth` to decide
    when to wrap elements onto a new row, but there's no `screen` global in
    QuickJS at all, so this raised 'ReferenceError: screen is not defined'
    (issue #15)."""
    svg = mermaidx.render(
        "C4Context\n"
        'title System Context diagram\n'
        'Person(customerA, "Customer A", "A bank customer.")\n'
        'System(SystemAA, "Banking System", "Lets customers view accounts.")\n'
        'Rel(customerA, SystemAA, "Uses")\n'
    ).svg()
    assert svg.startswith("<svg")


def test_multiline_html_label_flowchart_renders():
    """Regression: multi-line node labels containing embedded HTML (e.g.
    <code>...</code>) go through mermaid's grapheme-splitting helper, which
    feature-detects `Intl.Segmenter` -- but QuickJS has no `Intl` global at
    all (not even as an empty object), so reading `Intl.Segmenter` itself
    raised 'ReferenceError: Intl is not defined' before the fallback ever
    ran (issue #16)."""
    svg = mermaidx.render(
        'flowchart\n'
        '    a["line one\\n<code>line two</code>"]\n'
        '    b["<code>x = 1;</code>"]\n'
        '    a --> b\n'
    ).svg()
    assert svg.startswith("<svg")


def test_embed_font_without_fonttools_raises_clear_error(monkeypatch):
    """Regression: embed_font=True needs fontTools, which isn't a core
    dependency -- must fail with install instructions, not a bare
    ModuleNotFoundError (issue #12)."""
    import sys
    monkeypatch.setitem(sys.modules, "fontTools", None)
    monkeypatch.setitem(sys.modules, "fontTools.subset", None)
    d = mermaidx.render(FLOWCHART)
    with pytest.raises(ImportError, match=r"mermaidx\[embed\]"):
        d.svg(embed_font=True)


def test_embed_font_adds_matching_font_face():
    """Regression (issue #12): the plain SVG's CSS asks for whatever
    font-family mermaid's theme picked (e.g. "trebuchet ms"), which a
    browser won't have with the same metrics as the bundled DejaVu Sans
    used to lay the diagram out -- embed_font=True must register the
    embedded font under that *same* family name so the browser's lookup
    actually picks it up, not some unrelated name."""
    pytest.importorskip("fontTools")
    d = mermaidx.render(FLOWCHART)
    plain = d.svg()
    embedded = d.svg(embed_font=True)
    assert embedded != plain
    assert embedded.startswith("<svg")
    assert "@font-face" in embedded
    assert 'font-family:"trebuchet ms"' in embedded
    assert "data:font/ttf;base64," in embedded

    import xml.etree.ElementTree as ET
    ET.fromstring(embedded)  # must still be well-formed XML


def test_embed_font_is_cached_separately_from_plain_svg():
    pytest.importorskip("fontTools")
    d = mermaidx.render(FLOWCHART)
    assert d.svg() is d.svg()
    assert d.svg(embed_font=True) is d.svg(embed_font=True)
    assert d.svg() != d.svg(embed_font=True)


def test_embed_font_does_not_affect_png():
    """.png()/.pdf() already guarantee measure == paint via resvg's own
    font override (see raster.py) regardless of embed_font -- this option
    only matters for opening the raw SVG in a browser."""
    pytest.importorskip("fontTools")
    d = mermaidx.render(FLOWCHART)
    assert d.png() == d.png()  # cache key for png() is untouched by embed_font


def test_save_svg_forwards_embed_font(tmp_path):
    pytest.importorskip("fontTools")
    d = mermaidx.render(FLOWCHART)
    out = tmp_path / "out.svg"
    d.save(str(out), embed_font=True)
    assert "@font-face" in out.read_text(encoding="utf-8")


def _first_node_box_height(svg: str) -> float:
    import re
    return float(re.findall(r'label-container[^>]*height="([0-9.]+)"', svg)[0])


def test_multiline_node_label_grows_box_height():
    """A node label with <br> line breaks must produce a taller box than a
    single-line label. Regression: the headless bbox shim measured the whole
    <text> as one line, so multi-line boxes stayed single-line height and
    lines after the first overflowed the box border (issue #8)."""
    h1 = _first_node_box_height(
        mermaidx.render("stateDiagram-v2\n s1: One line\n [*] --> s1").svg())
    h2 = _first_node_box_height(
        mermaidx.render("stateDiagram-v2\n s1: Line one<br>line two\n [*] --> s1").svg())
    h3 = _first_node_box_height(
        mermaidx.render("stateDiagram-v2\n s1: a<br>b<br>c\n [*] --> s1").svg())
    assert h2 > h1, "2-line box should be taller than 1-line"
    assert h3 > h2, "3-line box should be taller than 2-line"
    # Each extra line adds roughly one line-step (dy=1.1em) — evenly spaced.
    assert (h2 - h1) == pytest.approx(h3 - h2, rel=0.2)


TREEMAP = (
    'treemap-beta\n'
    '    "Section 1"\n'
    '        "Leaf 1.1": 12\n'
    '        "Section 1.2"\n'
    '        "Leaf 1.2.1": 12\n'
    '    "Section 2"\n'
    '        "Leaf 2.1": 20\n'
    '        "Leaf 2.2": 25\n'
)

VENN = (
    'venn-beta\n'
    '  title "Team overlap"\n'
    '  set Frontend\n'
    '  set Backend\n'
    '  union Frontend,Backend["APIs"]\n'
)


def test_treemap_renders_without_error():
    """Regression for issue #19: element.ownerDocument.defaultView was
    missing from the DOM shim, so d3's cross-window getComputedStyle
    helper (`e.ownerDocument.defaultView.getComputedStyle(...)`) crashed
    with "cannot read property 'getComputedStyle' of undefined"."""
    svg = mermaidx.render(TREEMAP).svg()
    assert svg.startswith("<svg")
    for label in ("Section 1", "Section 2", "Leaf 1.1", "Leaf 2.2"):
        assert label in svg


def test_treemap_rasterizes_without_duplicate_style_attribute():
    """Regression: once #19 was fixed, the treemap label styling combined
    an attribute set via setAttribute('style', ...) with one set via the
    live el.style API, and the (old) serializer emitted two separate
    style="..." attributes on the same element -- invalid SVG/XML that
    resvg rejected with "attribute 'style' ... already defined"."""
    png = mermaidx.render(TREEMAP).png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_venn_renders_without_error():
    """Regression for issue #21: mermaid's venn diagram calls the modern
    Element.append() (distinct from appendChild(), accepts multiple args
    and bare strings) while wrapping set labels, which the DOM shim's Node
    class never implemented, crashing with "TypeError: not a function"."""
    svg = mermaidx.render(VENN).svg()
    assert svg.startswith("<svg")
    for label in ("Frontend", "Backend", "APIs"):
        assert label in svg


def test_venn_rasterizes():
    png = mermaidx.render(VENN).png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_multiline_edge_label_is_centered_on_its_background():
    """Regression for issue #17: a multi-line edge label (e.g. "Two
    line<br/>edge comment") rendered with its text baseline well outside
    its own background rectangle instead of centered inside it.

    Root cause: __resolveTextPos() finds the tspan that really carries a
    text element's paint position by walking down through single-child
    chains. That works for one-line labels (a single positioning tspan),
    but a multi-line label has one row-tspan PER LINE, so the walk broke
    immediately at the outer <text> element and used its vestigial,
    non-"em" y attribute instead of the first row's real y="...em"
    dy="1.1em" position -- putting the computed bbox (and therefore the
    centering transform) tens of pixels off from where the text actually
    paints.

    This asserts the label's own background rect really encloses (rather
    than merely sits near) the text after the two are combined by their
    respective transforms -- computed straight from the raw SVG so it
    catches a regression even if both elements "look" present.
    """
    import re

    code = (
        "graph TB\n"
        '    od>Odd shape]-- Two line<br/>edge comment --> ro(Rounded shape)\n'
    )
    svg = mermaidx.render(code).svg()

    # Locate the edge label's own <g transform="translate(dx, dy)"> (the
    # centering transform) and, inside it, the background rect plus the
    # first row's accumulated y (own y="...em" + dy="1.1em").
    m = re.search(
        r'<g class="label"[^>]*transform="translate\(([-\d.]+), ?([-\d.]+)\)">'
        r'.*?<rect class="background" x="([-\d.]+)" y="([-\d.]+)" '
        r'width="([-\d.]+)" height="([-\d.]+)">',
        svg, re.S,
    )
    assert m, "expected a positioned edge label with a background rect"
    dx, dy, rx, ry, rw, rh = (float(v) for v in m.groups())

    # First row tspan: y="-0.1em" dy="1.1em" -> real font-size units.
    row = re.search(r'<text[^>]*>\s*<tspan[^>]*y="(-?[\d.]+)em"[^>]*dy="([\d.]+)em"', svg)
    assert row, "expected the first row tspan with y/dy in em units"
    font_size_guess = 16  # mermaid's default flowchart edge-label font-size
    row_y = (float(row.group(1)) + float(row.group(2))) * font_size_guess

    text_absolute_y = dy + row_y
    rect_top = dy + ry
    rect_bottom = dy + ry + rh

    assert rect_top <= text_absolute_y <= rect_bottom, (
        f"text baseline y={text_absolute_y} falls outside its own "
        f"background rect [{rect_top}, {rect_bottom}]"
    )