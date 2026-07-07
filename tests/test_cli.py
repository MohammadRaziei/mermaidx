"""
Tests for the mmdc CLI.

Strategy:
- Argument parsing / exit codes: subprocess (fast, no PhantomJS needed)
- Actual conversion: module-scoped MermaidConverter (one PhantomJS process)
  called directly, avoiding per-test subprocess overhead.
- A small set of true end-to-end subprocess tests verify the __main__ wiring.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import pytest_asyncio

from mmdc import MermaidConverter


# ── fixtures ──────────────────────────────────────────────────────────────────

BASIC_MERMAID = Path(__file__).parent / "basic.mermaid"
SIMPLE   = "graph LR\n    A --> B"
FLOWCHART = "graph TD\n    A[Start] --> B{Yes?}\n    B -->|Yes| C[OK]\n    B -->|No| D[Fail]"


def run(*args, input: str = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mmdc", *args],
        capture_output=True, text=True, input=input,
    )


def _png_dims(data: bytes):
    assert data[:4] == b"\x89PNG"
    return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]


@pytest_asyncio.fixture(scope="module")
async def m():
    """One PhantomJS process shared across all conversion tests."""
    async with MermaidConverter() as converter:
        yield converter


# ── argument parsing / exit codes (subprocess — fast) ────────────────────────

def test_version():
    r = run("--version")
    assert r.returncode == 0
    assert r.stdout.strip().count(".") >= 1


def test_short_version():
    r = run("-V")
    assert r.stdout.strip() == run("--version").stdout.strip()


def test_help():
    r = run("--help")
    assert r.returncode == 0
    assert "mmdc" in r.stdout


def test_info():
    r = run("--info")
    assert r.returncode == 0
    assert re.match(r"^v?\d+\.\d+\.\d+", r.stdout.strip())


def test_info_matches_rendering_info_diagram_directly():
    """
    `--info` extracts text from the rendered "info" diagram internally.
    `echo "info" | mmdc -i -` renders that exact same diagram through the
    normal (non-shortcut) code path and writes raw SVG to stdout. Both must
    report the same Mermaid version.
    """
    info_flag = run("--info")
    assert info_flag.returncode == 0
    version_from_flag = info_flag.stdout.strip()

    piped = run("-i", "-", input="info")
    assert piped.returncode == 0
    assert piped.stdout.lstrip().startswith("<svg")

    root = ET.fromstring(piped.stdout)
    texts = [
        el.text.strip()
        for el in root.iter()
        if el.tag.split("}")[-1] == "text" and el.text and el.text.strip()
    ]
    version_from_pipe = " ".join(texts)

    assert version_from_pipe == version_from_flag


def test_no_args_exits_nonzero():
    assert run().returncode != 0


def test_missing_input_exits_nonzero():
    assert run("-o", "out.svg").returncode != 0


def test_missing_output_writes_svg_to_stdout():
    """No -o means SVG goes to stdout."""
    r = run("-i", str(BASIC_MERMAID))
    assert r.returncode == 0
    assert r.stdout.lstrip().startswith("<svg")


# ── SVG (via shared converter) ────────────────────────────────────────────────

async def test_svg_from_string(m):
    data = await m.to_svg(SIMPLE)
    assert data.lstrip().startswith(b"<svg")


async def test_svg_from_file(m):
    data = await m.to_svg(BASIC_MERMAID)
    assert data.lstrip().startswith(b"<svg")


async def test_svg_from_path_object(m):
    data = await m.to_svg(Path(BASIC_MERMAID))
    assert data.lstrip().startswith(b"<svg")


async def test_svg_writes_file(m, tmp_path):
    out = tmp_path / "out.svg"
    data = await m.to_svg(SIMPLE, out)
    assert out.exists() and data == out.read_bytes()


async def test_svg_theme_dark(m):
    assert (await m.to_svg(SIMPLE, theme="dark")).lstrip().startswith(b"<svg")


async def test_svg_theme_forest(m):
    assert (await m.to_svg(SIMPLE, theme="forest")).lstrip().startswith(b"<svg")


async def test_svg_theme_neutral(m):
    assert (await m.to_svg(SIMPLE, theme="neutral")).lstrip().startswith(b"<svg")


# ── PNG (via shared converter) ────────────────────────────────────────────────

async def test_png_from_string(m):
    assert (await m.to_png(SIMPLE))[:4] == b"\x89PNG"


async def test_png_from_file(m):
    assert (await m.to_png(BASIC_MERMAID))[:4] == b"\x89PNG"


async def test_png_writes_file(m, tmp_path):
    out = tmp_path / "out.png"
    data = await m.to_png(SIMPLE, out)
    assert out.exists() and data == out.read_bytes()


async def test_png_scale(m):
    w1, h1 = _png_dims(await m.to_png(SIMPLE, scale=1.0))
    w2, h2 = _png_dims(await m.to_png(SIMPLE, scale=2.0))
    assert abs(w2 - w1 * 2) <= 1
    assert abs(h2 - h1 * 2) <= 1


async def test_png_theme(m):
    assert (await m.to_png(SIMPLE, theme="dark"))[:4] == b"\x89PNG"


async def test_png_background(m):
    assert (await m.to_png(SIMPLE, background="#f0f0f0"))[:4] == b"\x89PNG"


async def test_png_flowchart(m):
    assert (await m.to_png(FLOWCHART))[:4] == b"\x89PNG"


# ── PDF (via shared converter) ────────────────────────────────────────────────

async def test_pdf_from_string(m):
    assert (await m.to_pdf(SIMPLE))[:4] == b"%PDF"


async def test_pdf_from_file(m):
    assert (await m.to_pdf(BASIC_MERMAID))[:4] == b"%PDF"


async def test_pdf_writes_file(m, tmp_path):
    out = tmp_path / "out.pdf"
    data = await m.to_pdf(SIMPLE, out)
    assert out.exists() and data == out.read_bytes()


async def test_pdf_fit_mode(m):
    assert (await m.to_pdf(SIMPLE))[:4] == b"%PDF"


async def test_pdf_a4(m):
    assert (await m.to_pdf(SIMPLE, pdf_format="A4"))[:4] == b"%PDF"


async def test_pdf_landscape(m):
    assert (await m.to_pdf(SIMPLE, pdf_format="A4", pdf_landscape=True))[:4] == b"%PDF"


async def test_pdf_margin(m):
    assert (await m.to_pdf(SIMPLE, pdf_margin="1cm"))[:4] == b"%PDF"


# ── config / css (via shared converter) ───────────────────────────────────────

async def test_config_dict(m):
    data = await m.to_svg(SIMPLE, config={"theme": "forest"})
    assert data.lstrip().startswith(b"<svg")


async def test_css_string(m):
    data = await m.to_svg(SIMPLE, css=".node rect { fill: red; }")
    assert data.lstrip().startswith(b"<svg")


# ── convert (via shared converter) ───────────────────────────────────────────

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


# ── end-to-end subprocess (just wiring — one per format) ─────────────────────

def test_e2e_svg(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_e2e_png(tmp_path):
    out = tmp_path / "out.png"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_e2e_pdf(tmp_path):
    out = tmp_path / "out.pdf"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_e2e_stdin(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", "-", "-o", str(out), input=SIMPLE)
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_e2e_output_message(tmp_path):
    out = tmp_path / "result.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert "result.svg" in r.stderr
    