"""
Tests for MermaidConverter — async persistent session.
All tests use a module-scoped converter (one PhantomJS process for the suite).
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
import pytest_asyncio

from mmdc import MermaidConverter


# ── sample diagrams ───────────────────────────────────────────────────────────

FLOWCHART = "graph TD\n    A[Start] --> B{Decision}\n    B -->|Yes| C[OK]\n    B -->|No| D[Fail]"

SEQUENCE = "sequenceDiagram\n    Alice->>Bob: Hello\n    Bob-->>Alice: Hi there"

SIMPLE = "graph LR\n    A --> B"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def m():
    """One MermaidConverter (= one PhantomJS process) shared across the module."""
    async with MermaidConverter() as converter:
        yield converter


# ── lifecycle ─────────────────────────────────────────────────────────────────

async def test_context_manager():
    async with MermaidConverter() as c:
        svg = await c.to_svg(SIMPLE)
        assert b"<svg" in svg


async def test_manual_start_close():
    c = MermaidConverter()
    await c.start()
    svg = await c.to_svg(SIMPLE)
    assert b"<svg" in svg
    await c.close()


async def test_not_started_raises():
    c = MermaidConverter()
    with pytest.raises(RuntimeError, match="not started"):
        await c.to_svg(SIMPLE)


async def test_double_close_is_safe():
    c = MermaidConverter()
    await c.start()
    await c.close()
    await c.close()


# ── SVG ───────────────────────────────────────────────────────────────────────

async def test_to_svg_returns_bytes(m):
    svg = await m.to_svg(FLOWCHART)
    assert isinstance(svg, bytes) and len(svg) > 0


async def test_to_svg_is_valid_svg(m):
    svg = await m.to_svg(FLOWCHART)
    assert svg.lstrip().startswith(b"<svg")


async def test_to_svg_writes_file(m, tmp_path):
    out = tmp_path / "diagram.svg"
    data = await m.to_svg(FLOWCHART, out)
    assert out.exists()
    assert data == out.read_bytes()


async def test_to_svg_from_file(m, tmp_path):
    f = tmp_path / "diagram.mermaid"
    f.write_text(FLOWCHART, encoding="utf-8")
    svg = await m.to_svg(f)
    assert b"<svg" in svg


async def test_to_svg_from_path_object(m, tmp_path):
    f = tmp_path / "diagram.mermaid"
    f.write_text(FLOWCHART, encoding="utf-8")
    svg = await m.to_svg(Path(f))
    assert b"<svg" in svg


async def test_to_svg_theme_default(m):
    svg = await m.to_svg(SIMPLE, theme="default")
    assert b"<svg" in svg


async def test_to_svg_theme_dark(m):
    svg = await m.to_svg(SIMPLE, theme="dark")
    assert b"<svg" in svg


async def test_to_svg_theme_forest(m):
    svg = await m.to_svg(SIMPLE, theme="forest")
    assert b"<svg" in svg


async def test_to_svg_sequence(m):
    svg = await m.to_svg(SEQUENCE)
    assert b"<svg" in svg


async def test_to_svg_batch_reuses_process(m):
    """Multiple renders should all succeed without restarting PhantomJS."""
    results = [await m.to_svg(SIMPLE) for _ in range(5)]
    assert all(b"<svg" in r for r in results)


# ── PNG ───────────────────────────────────────────────────────────────────────

def _png_dims(data: bytes):
    assert data[:4] == b"\x89PNG"
    return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]


async def test_to_png_magic(m):
    assert (await m.to_png(SIMPLE))[:4] == b"\x89PNG"


async def test_to_png_writes_file(m, tmp_path):
    out = tmp_path / "diagram.png"
    data = await m.to_png(SIMPLE, out)
    assert out.exists()
    assert data == out.read_bytes()


async def test_to_png_scale(m):
    png_1x = await m.to_png(SIMPLE, scale=1.0)
    png_2x = await m.to_png(SIMPLE, scale=2.0)
    w1, h1 = _png_dims(png_1x)
    w2, h2 = _png_dims(png_2x)
    assert abs(w2 - w1 * 2) <= 1
    assert abs(h2 - h1 * 2) <= 1


async def test_to_png_theme(m):
    assert (await m.to_png(SIMPLE, theme="dark"))[:4] == b"\x89PNG"


async def test_to_png_flowchart(m):
    assert (await m.to_png(FLOWCHART))[:4] == b"\x89PNG"


async def test_to_png_sequence(m):
    assert (await m.to_png(SEQUENCE))[:4] == b"\x89PNG"


# ── PDF ───────────────────────────────────────────────────────────────────────

async def test_to_pdf_magic(m):
    assert (await m.to_pdf(SIMPLE))[:4] == b"%PDF"


async def test_to_pdf_writes_file(m, tmp_path):
    out = tmp_path / "diagram.pdf"
    data = await m.to_pdf(SIMPLE, out)
    assert out.exists()
    assert data == out.read_bytes()


async def test_to_pdf_fit(m):
    """Default (pdf_format=None) fits paper to diagram size."""
    assert (await m.to_pdf(SIMPLE))[:4] == b"%PDF"


async def test_to_pdf_a4(m):
    assert (await m.to_pdf(SIMPLE, pdf_format="A4"))[:4] == b"%PDF"


async def test_to_pdf_landscape(m):
    assert (await m.to_pdf(SIMPLE, pdf_format="A4", pdf_landscape=True))[:4] == b"%PDF"


async def test_to_pdf_flowchart(m):
    assert (await m.to_pdf(FLOWCHART))[:4] == b"%PDF"


# ── convert ───────────────────────────────────────────────────────────────────

async def test_convert_svg(m, tmp_path):
    out = tmp_path / "out.svg"
    await m.convert(SIMPLE, out)
    assert out.read_bytes().lstrip().startswith(b"<svg")


async def test_convert_png(m, tmp_path):
    out = tmp_path / "out.png"
    await m.convert(SIMPLE, out)
    assert out.read_bytes()[:4] == b"\x89PNG"


async def test_convert_pdf(m, tmp_path):
    out = tmp_path / "out.pdf"
    await m.convert(SIMPLE, out)
    assert out.read_bytes()[:4] == b"%PDF"


async def test_convert_no_output_returns_svg(m):
    result = await m.convert(SIMPLE)
    assert b"<svg" in result


async def test_convert_unknown_extension_raises(m):
    with pytest.raises(ValueError, match="Unsupported"):
        await m.convert(SIMPLE, Path("out.xyz"))


# ── default theme / background ────────────────────────────────────────────────

async def test_default_theme_set_at_init():
    async with MermaidConverter(theme="forest") as c:
        svg = await c.to_svg(SIMPLE)
        assert b"<svg" in svg


async def test_default_background_set_at_init():
    async with MermaidConverter(background="#f0f0f0") as c:
        png = await c.to_png(SIMPLE)
        assert png[:4] == b"\x89PNG"
