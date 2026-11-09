#!/usr/bin/env python3
"""Render the landing-page showcase with mermaidx itself.

Reads a few diagrams from tests/samples and renders each one with every backend, so the page can switch the
backend of a diagram. Writes
    docs/static/img/showcase/<id>.<backend>.png      (a backend that cannot draw the diagram gets no image)
    docs/src/data/showcase.json                      (backends, and for each diagram: label, source, one entry
                                                      per backend with the image size or the error)

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

# The order of the switch on the page; the first one is the default and is shown without `backend=` in the code.
BACKENDS = ["js:mermaid", "js:pele", "rust:merman", "rust:mermaid-rs-renderer"]

available = [b for b in BACKENDS if b in mermaidx.backends()]
IMG_DIR.mkdir(parents=True, exist_ok=True)
DATA.parent.mkdir(parents=True, exist_ok=True)  # absent on a fresh checkout: git does not keep empty folders
for old in IMG_DIR.glob("*.png"):  # the images of an earlier run, whatever their name
    old.unlink()

slides = []
for sample_id, label in SLIDES:
    source = (SAMPLES / f"{sample_id}.mmd").read_text(encoding="utf-8").strip("\n")
    variants = []
    for backend in available:
        try:
            png = mermaidx.render(source, backend=backend).png(scale=2.0, background="#ffffff")
        except Exception as exc:  # a backend that does not know this diagram type: the page says so
            message = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:160]
            variants.append({"backend": backend, "error": message})
            print(f"{label:<14} {backend:<26} not drawn: {message}")  # noqa: T201
            continue
        name = f"{sample_id}.{backend.replace(':', '-')}.png"
        (IMG_DIR / name).write_bytes(png)
        width, height = struct.unpack(">II", png[16:24])
        variants.append({"backend": backend, "image": f"img/showcase/{name}", "width": width, "height": height})
        print(f"{label:<14} {backend:<26} {width}x{height}  {len(png) // 1024} KB")  # noqa: T201
    slides.append({"id": sample_id, "label": label, "source": source, "variants": variants})

DATA.write_text(json.dumps({"backends": available, "slides": slides}, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8")
