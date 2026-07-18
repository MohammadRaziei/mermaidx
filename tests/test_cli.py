"""
Tests for the mermaidx CLI.

Everything here is either a direct subprocess call (real end-to-end CLI
wiring) or a direct call into mermaidx.render() (conversion logic, without the
subprocess overhead). There's no async fixture anymore -- rendering is
CPU-bound and synchronous end to end, so a plain module-level helper is
enough; no shared "session" object needs to be kept alive across tests.
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

from mermaidx import render

BASIC_MERMAID = Path(__file__).parent / "basic.mermaid"
SIMPLE = "graph LR\n    A --> B"
FLOWCHART = "graph TD\n    A[Start] --> B{Yes?}\n    B -->|Yes| C[OK]\n    B -->|No| D[Fail]"


def run(*args, input: str = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mermaidx", *args],
        capture_output=True, text=True, input=input,
    )


def _png_dims(data: bytes):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">I", data[16:20])[0], struct.unpack(">I", data[20:24])[0]


# ── argument parsing / exit codes ────────────────────────────────────────────

def test_version():
    r = run("--version")
    assert r.returncode == 0
    assert r.stdout.strip().count(".") >= 1


def test_short_version():
    r = run("-v")
    assert r.stdout.strip() == run("--version").stdout.strip()


def test_help():
    r = run("--help")
    assert r.returncode == 0
    assert "mermaidx" in r.stdout


def test_info():
    r = run("--info")
    assert r.returncode == 0
    assert re.match(r"^v?\d+\.\d+\.\d+", r.stdout.strip())


def test_info_matches_rendering_info_diagram_directly():
    """
    `--info` extracts text from the rendered "info" diagram internally.
    `echo "info" | mermaidx -i -` renders that exact same diagram through the
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
    assert " ".join(texts) == version_from_flag


def test_no_args_exits_nonzero():
    assert run().returncode != 0


def test_missing_input_exits_nonzero():
    assert run("-o", "out.svg").returncode != 0


def test_missing_output_writes_svg_to_stdout():
    r = run("-i", str(BASIC_MERMAID))
    assert r.returncode == 0
    assert r.stdout.lstrip().startswith("<svg")


def test_invalid_mermaid_exits_nonzero():
    r = run("-i", "-", input="this is not valid mermaid {{{")
    assert r.returncode != 0


# ── SVG (direct render() calls) ───────────────────────────────────────────────

def test_svg_from_string():
    assert render(SIMPLE).svg().startswith("<svg")


def test_svg_writes_file(tmp_path):
    out = tmp_path / "out.svg"
    render(SIMPLE).save(str(out))
    assert out.read_text().startswith("<svg")


def test_svg_theme_dark():
    assert render(SIMPLE, theme="dark").svg().startswith("<svg")


def test_svg_theme_forest():
    assert render(SIMPLE, theme="forest").svg().startswith("<svg")


def test_svg_theme_neutral():
    assert render(SIMPLE, theme="neutral").svg().startswith("<svg")


# ── PNG ───────────────────────────────────────────────────────────────────────

def test_png_from_string():
    assert render(SIMPLE).png()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_writes_file(tmp_path):
    out = tmp_path / "out.png"
    render(SIMPLE).save(str(out))
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_scale():
    w1, h1 = _png_dims(render(SIMPLE).png())
    w2, h2 = _png_dims(render(SIMPLE).png(scale=2.0))
    assert abs(w2 - w1 * 2) <= 1
    assert abs(h2 - h1 * 2) <= 1


def test_png_width():
    w, h = _png_dims(render(SIMPLE).png(width=400))
    assert w == 400


def test_png_theme():
    assert render(SIMPLE, theme="dark").png()[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_background():
    assert render(SIMPLE).png(background="#f0f0f0")[:8] == b"\x89PNG\r\n\x1a\n"


def test_png_flowchart():
    assert render(FLOWCHART).png()[:8] == b"\x89PNG\r\n\x1a\n"


# ── PDF ───────────────────────────────────────────────────────────────────────

def test_pdf_from_string():
    assert render(SIMPLE).pdf()[:5] == b"%PDF-"


def test_pdf_writes_file(tmp_path):
    out = tmp_path / "out.pdf"
    render(SIMPLE).save(str(out))
    assert out.read_bytes()[:5] == b"%PDF-"


def test_pdf_fit_mode():
    assert render(SIMPLE).pdf()[:5] == b"%PDF-"


def test_pdf_a4():
    assert render(SIMPLE).pdf(pdf_format="A4")[:5] == b"%PDF-"


def test_pdf_landscape():
    assert render(SIMPLE).pdf(pdf_format="A4", pdf_landscape=True)[:5] == b"%PDF-"


def test_pdf_margin():
    assert render(SIMPLE).pdf(pdf_margin="1cm")[:5] == b"%PDF-"


# ── config / css ──────────────────────────────────────────────────────────────

def test_config_dict():
    assert render(SIMPLE, config={"theme": "forest"}).svg().startswith("<svg")


def test_css_string():
    assert render(SIMPLE, css=".node rect { fill: red; }").svg().startswith("<svg")


# ── save() format dispatch ────────────────────────────────────────────────────

def test_save_svg(tmp_path):
    out = tmp_path / "out.svg"
    render(SIMPLE).save(str(out))
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_save_png(tmp_path):
    out = tmp_path / "out.png"
    render(SIMPLE).save(str(out))
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_pdf(tmp_path):
    out = tmp_path / "out.pdf"
    render(SIMPLE).save(str(out))
    assert out.read_bytes()[:5] == b"%PDF-"


def test_save_unknown_extension_raises(tmp_path):
    with pytest.raises(ValueError, match="Unsupported|Cannot infer"):
        render(SIMPLE).save(str(tmp_path / "out.xyz"))


# ── end-to-end subprocess (CLI wiring) ────────────────────────────────────────

def test_e2e_svg(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_e2e_png(tmp_path):
    out = tmp_path / "out.png"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_e2e_png_width(tmp_path):
    out = tmp_path / "out.png"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out), "-w", "500")
    assert r.returncode == 0
    w, _ = _png_dims(out.read_bytes())
    assert w == 500


def test_e2e_pdf(tmp_path):
    out = tmp_path / "out.pdf"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out))
    assert r.returncode == 0
    assert out.read_bytes()[:5] == b"%PDF-"


def test_e2e_pdf_a4_landscape(tmp_path):
    out = tmp_path / "out.pdf"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out), "--pdf-format", "A4", "--landscape")
    assert r.returncode == 0
    assert out.read_bytes()[:5] == b"%PDF-"


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


def test_e2e_quiet_suppresses_output_message(tmp_path):
    out = tmp_path / "result.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out), "-q")
    assert r.returncode == 0
    assert r.stderr == ""
    assert out.read_bytes().lstrip().startswith(b"<svg")


def test_e2e_quiet_long_flag_suppresses_output_message(tmp_path):
    out = tmp_path / "result.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out), "--quiet")
    assert r.returncode == 0
    assert r.stderr == ""


def test_e2e_config_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"theme": "forest"}))
    r = run("-i", str(BASIC_MERMAID), "--config", str(config_path))
    assert r.returncode == 0
    assert r.stdout.lstrip().startswith("<svg")


def test_e2e_css_file(tmp_path):
    css_path = tmp_path / "style.css"
    css_path.write_text(".node rect { fill: red; }")
    r = run("-i", str(BASIC_MERMAID), "--css", str(css_path))
    assert r.returncode == 0
    assert r.stdout.lstrip().startswith("<svg")


# ── backends / verbose ────────────────────────────────────────────────────

def test_list_backends():
    r = run("--list-backends")
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert any(line.startswith("quickjs") for line in lines)
    assert any("(default)" in line for line in lines)


def test_backend_quickjs_explicit(tmp_path):
    out = tmp_path / "out.svg"
    r = run("-i", str(BASIC_MERMAID), "-o", str(out), "--backend", "quickjs")
    assert r.returncode == 0
    assert out.read_bytes().lstrip().startswith(b"<svg")
    