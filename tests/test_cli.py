"""
Tests for the mmdc CLI (python -m mmdc).
All tests use subprocess so they test the real CLI entry point.
"""

from __future__ import annotations

import subprocess
import sys
import struct
from pathlib import Path

import pytest


# ── helper ────────────────────────────────────────────────────────────────────

BASIC_MERMAID = Path(__file__).parent / "basic.mermaid"

SIMPLE = "graph LR\n    A --> B"
FLOWCHART = "graph TD\n    A[Start] --> B{Yes?}\n    B -->|Yes| C[OK]\n    B -->|No| D[Fail]"


def run(*args, input: str = None) -> subprocess.CompletedProcess:
    """Run `python -m mmdc <args>` and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "mmdc", *args],
        capture_output=True,
        text=True,
        input=input,
    )


def _png_dims(data: bytes):
    assert data[:4] == b"\x89PNG"
    return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]


# ── top-level ─────────────────────────────────────────────────────────────────

def test_version():
    r = run("--version")
    assert r.returncode == 0
    assert r.stdout.strip().count(".") >= 1


def test_short_version():
    r = run("-V")
    assert r.returncode == 0
    assert r.stdout.strip() == run("--version").stdout.strip()


def test_help():
    r = run("--help")
    assert r.returncode == 0
    assert "mmdc" in r.stdout


def test_no_args_exits_nonzero():
    r = run()
    assert r.returncode != 0


# ── SVG ───────────────────────────────────────────────────────────────────────

def test_svg_from_file(tmp_path):
    f = tmp_path / "diagram.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert out.exists()
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_svg_from_stdin(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", "-", "-o", str(out), input=SIMPLE)
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_svg_from_basic_mermaid(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_svg_theme_dark(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out), "--theme", "dark")
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_svg_theme_forest(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out), "--theme", "forest")
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_svg_theme_neutral(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out), "--theme", "neutral")
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


# ── PNG ───────────────────────────────────────────────────────────────────────

def test_png_from_file(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.png"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_png_from_stdin(tmp_path):
    out = tmp_path / "out.png"
    r = run("-i", "-", "-o", str(out), input=SIMPLE)
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_png_scale(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")

    out_1x = tmp_path / "out_1x.png"
    out_2x = tmp_path / "out_2x.png"

    run("-i", str(f), "-o", str(out_1x), "--scale", "1.0")
    run("-i", str(f), "-o", str(out_2x), "--scale", "2.0")

    w1, h1 = _png_dims(out_1x.read_bytes())
    w2, h2 = _png_dims(out_2x.read_bytes())

    assert w2 == w1 * 2
    assert h2 == h1 * 2


def test_png_theme(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.png"
    r = run("-i", str(f), "-o", str(out), "--theme", "dark")
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_png_background(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.png"
    r = run("-i", str(f), "-o", str(out), "--background", "#f0f0f0")
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_png_flowchart(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(FLOWCHART, encoding="utf-8")
    out = tmp_path / "out.png"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"\x89PNG"


# ── PDF ───────────────────────────────────────────────────────────────────────

def test_pdf_from_file(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_from_stdin(tmp_path):
    out = tmp_path / "out.pdf"
    r = run("-i", "-", "-o", str(out), input=SIMPLE)
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_fit_mode(tmp_path):
    """Default: no --pdf-format means paper fits diagram size."""
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_a4(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    r = run("-i", str(f), "-o", str(out), "--pdf-format", "A4")
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_landscape(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    r = run("-i", str(f), "-o", str(out), "--pdf-format", "A4", "--landscape")
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


def test_pdf_margin(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "out.pdf"
    r = run("-i", str(f), "-o", str(out), "--margin", "1cm")
    assert r.returncode == 0
    assert out.read_bytes()[:4] == b"%PDF"


# ── config / css ──────────────────────────────────────────────────────────────

def test_config_file(tmp_path):
    import json
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"theme": "forest"}), encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out), "--config", str(cfg))
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_css_file(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    css = tmp_path / "style.css"
    css.write_text(".node rect { fill: #ff0000; }", encoding="utf-8")
    out = tmp_path / "out.svg"
    r = run("-i", str(f), "-o", str(out), "--css", str(css))
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


# ── output message ────────────────────────────────────────────────────────────

def test_output_message_contains_filename(tmp_path):
    f = tmp_path / "d.mermaid"
    f.write_text(SIMPLE, encoding="utf-8")
    out = tmp_path / "result.svg"
    r = run("-i", str(f), "-o", str(out))
    assert r.returncode == 0
    assert "result.svg" in r.stdout
