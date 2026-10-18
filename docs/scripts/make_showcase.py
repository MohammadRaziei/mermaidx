#!/usr/bin/env python3
"""Render the landing-page showcase with mermaidx itself.

Reads a few diagrams from tests/samples and writes
    docs/static/img/showcase/<id>.png
    docs/src/data/showcase.json   (label, Python code, image size)

Run it again whenever you want to change the showcase or after a mermaidx upgrade:
    python docs/scripts/make_showcase.py
"""
import json
import struct
from pathlib import Path

import mermaidx

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "samples"
IMG_DIR = ROOT / "docs" / "static" / "img" / "showcase"
DATA = ROOT / "docs" / "src" / "data" / "showcase.json"

SLIDES = [
    ("06_complex_sequence", "Sequence"),
    ("27_architecture", "Architecture"),
    ("20_quadrant_chart", "Quadrant chart"),
    ("22_sankey", "Sankey"),
    ("31_venn", "Venn"),
    ("19_gitgraph", "Git graph"),
]

IMG_DIR.mkdir(parents=True, exist_ok=True)
DATA.parent.mkdir(parents=True, exist_ok=True)  # absent on a fresh checkout: git does not keep empty folders
out = []
for sample_id, label in SLIDES:
    source = (SAMPLES / f"{sample_id}.mmd").read_text(encoding="utf-8").strip("\n")
    png = mermaidx.render(source).png(scale=2.0, background="#ffffff")
    (IMG_DIR / f"{sample_id}.png").write_bytes(png)
    width, height = struct.unpack(">II", png[16:24])
    # What the visitor sees on the left: the Python call, with the diagram inside it.
    code = f'import mermaidx\n\ndiagram = mermaidx.render("""\n{source}\n""")\ndiagram.save("diagram.png")'
    out.append({"id": sample_id, "label": label, "code": code, "image": f"img/showcase/{sample_id}.png",
                "width": width, "height": height})
    print(f"{label:<12} {width}x{height}  {len(png) // 1024} KB")
DATA.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
