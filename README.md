# mmdc — Mermaid Diagram Converter for Python

[![PyPI](https://img.shields.io/pypi/v/mmdc.svg)](https://pypi.org/project/mmdc)
[![Python](https://img.shields.io/pypi/pyversions/mmdc.svg)](https://pypi.org/project/mmdc)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/MohammadRaziei/mmdc/actions/workflows/wheel.yml/badge.svg)](https://github.com/MohammadRaziei/mmdc/actions/workflows/wheel.yml)

<div align="center">
<img src="https://raw.githubusercontent.com/MohammadRaziei/mmdc/master/docs/static/img/logo.svg" width="150pt"/>
</div>

Convert Mermaid diagrams to SVG, PNG, and PDF — **fully offline and fast, just `pip install mmdc`**.

No Node.js. No npm. No Chrome. No system packages. Mermaid v11 runs inside a small embedded JS engine (QuickJS-ng), and every raster/PDF conversion goes through [resvg](https://github.com/RazrFalcon/resvg) — no Pillow, no Cairo, nothing to compile.

```bash
pip install mmdc
```

---

## Why mmdc?

The official Mermaid CLI (`@mermaid-js/mermaid-cli`) drives a real headless Chrome via Puppeteer. That works, but it's slow to start, heavy to install (~170MB+ of Chromium), and awkward to embed in a pipeline.

`mmdc` renders the actual, current Mermaid v11 JS library — not a reimplementation, not a subset — inside QuickJS-ng, a ~7MB embedded JS engine. Real text metrics (which a fake DOM can't fabricate on its own) come from a bundled font read directly via a small pure-Python TTF parser, and that *same* font is handed to resvg for final rendering — so layout and paint always agree, by construction.

---

## Quick Start

```python
import mmdc

d = mmdc.render("""
graph TD
    A[Install] --> B[Import]
    B --> C[Convert]
    C --> D[Done]
""")

d.save("diagram.svg")
d.save("diagram.png", scale=2.0)
d.save("diagram.pdf", pdf_format="A4")
```

```bash
mmdc -i diagram.mermaid -o diagram.svg
mmdc -i diagram.mermaid -o diagram.png --scale 2.0
cat diagram.mermaid | mmdc -i - -o diagram.pdf
```

---

## How It Works

```mermaid
flowchart LR
    A[Mermaid source] --> B[QuickJS-ng]
    B -->|"mermaid.js v11 (bundled)"| C[SVG]
    C --> D[resvg]
    D --> E[PNG]
    C --> F["hand-written PDF writer<br/>(stdlib only)"]
    F --> G[PDF]

    H[bundled DejaVu Sans] -.font metrics.-> B
    H -.same font, forced.-> D
```

Everything happens in one process, no subprocess, no I/O:

- **SVG** — mermaid.js runs inside QuickJS-ng against a minimal fake DOM/SVG implementation. The one thing a fake DOM can't fabricate — real text metrics (`getBBox`/`getComputedTextLength`) — is bridged back into Python, which reads real glyph widths from a bundled font.
- **PNG** — the SVG is rasterized by [resvg](https://pypi.org/project/resvg_py/), forced to use that *same* bundled font, so what mermaid measured during layout is exactly what gets painted.
- **PDF** — a small hand-written PDF writer (stdlib `zlib`/`struct` only) embeds the rendered pixels directly. No Pillow, no Cairo, no reportlab — every mainstream "put an image in a PDF" library pulls in Pillow as a transitive dependency; this avoids that entirely.

Rendering is CPU-bound, synchronous, single-process — there's no browser or subprocess to wait on, so there's nothing for `async` to usefully overlap. See [`mmdc.render_many()`](#parallel-batch-rendering) below for real parallelism instead.

---

## Python API

### `render(source, backend=None, **opts) -> Diagram`

```python
import mmdc

d = mmdc.render("flowchart LR; A-->B-->C")   # SVG is rendered immediately
```

`Diagram` methods — SVG is already computed; everything else is derived from it on demand:

| Method | Returns | Notes |
|---|---|---|
| `.svg()` | `str` | Already computed at `render()` time |
| `.png(width?, height?, scale?, background?)` | `bytes` | Aspect ratio always preserved |
| `.pdf(pdf_format?, pdf_landscape?, pdf_margin?, width?, height?, scale?, background?)` | `bytes` | `pdf_format=None` (default) fits the page to the diagram |
| `.raw(width?, height?, background?)` | `(bytes, w, h)` | Raw RGBA8888, no imaging library involved |
| `.numpy(width?, height?, background?)` | `np.ndarray` | `(H, W, 4)` uint8; requires `numpy` |
| `.save(path, ...)` | `None` | Format inferred from the extension: `.svg` / `.png` / `.pdf` |
| `._repr_svg_()` | `str` | Automatic inline rendering in Jupyter/IPython |

```python
d.png(width=1200, background="#ffffff")
d.raw()                 # (bytes, width, height) -- RGBA8888
d.numpy()                # np.ndarray, no Pillow needed
d.save("out.pdf", pdf_format="A4", pdf_margin="1cm")
```

### Themes, config, CSS

```python
mmdc.render(source, theme="dark")                    # "default" | "forest" | "dark" | "neutral"
mmdc.render(source, config={"flowchart": {"curve": "basis"}})
mmdc.render(source, css=".node rect { rx: 8; ry: 8; }")
```

### Parallel batch rendering

Rendering is pure CPU work — no I/O to overlap, so real concurrency means real processes, not `async`:

```python
diagrams = mmdc.render_many(sources, workers=4, theme="dark")
for d, name in zip(diagrams, output_names):
    d.save(name)
```

Each worker process starts its own persistent engine once and reuses it for every diagram routed to it.

### ASCII / terminal output (optional)

```bash
pip install mmdc[ascii]
```

```python
print(mmdc.render_ascii("graph LR; A-->B-->C"))
```
```
┌───┐    ┌───┐    ┌───┐
│ A ├───►│ B ├───►│ C │
└───┘    └───┘    └───┘
```

Backed by [termaid](https://pypi.org/project/termaid/) — pure Python, zero dependencies.

### Low-level utilities

Rasterize any SVG string directly, without going through `render()`:

```python
from mmdc import svg_to_png, svg_to_raw

svg = open("diagram.svg").read()
png = svg_to_png(svg, width=1200, background="#ffffff")
raw, w, h = svg_to_raw(svg)
```

### Additional backends (optional)

```bash
pip install mmdc[rust]
```

If [`mmdr`](https://github.com/mohammadraziei/mmdr) (a native-Rust Mermaid renderer) is installed, its backends become available too — same `Diagram` interface either way:

```python
mmdc.backends()
# ['js']                                   # mmdr not installed
# ['js', 'merman', 'mermaid-rs-renderer']   # mmdr installed

mmdc.render(source, backend="merman")   # returns mmdr's own Diagram directly
```

---

## CLI

```bash
# SVG to stdout (no -o needed)
mmdc -i diagram.mermaid
cat diagram.mermaid | mmdc -i -

# save to file (format from extension)
mmdc -i diagram.mermaid -o diagram.svg
mmdc -i diagram.mermaid -o diagram.png
mmdc -i diagram.mermaid -o diagram.pdf

# size
mmdc -i diagram.mermaid -o diagram.png -w 1200
mmdc -i diagram.mermaid -o diagram.png --scale 2.0

# theme & background
mmdc -i diagram.mermaid -o diagram.svg --theme dark
mmdc -i diagram.mermaid -o diagram.png --background "#f5f5f5"

# PDF options
mmdc -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape --margin 1cm

# config & CSS
mmdc -i diagram.mermaid -o diagram.svg --config config.json --css style.css

# info — Mermaid library version
mmdc --info

# version
mmdc --version
```

---

## Supported Diagram Types

Everything Mermaid v11 itself supports (this bundles the real library, not a subset):
flowcharts, sequence diagrams, class diagrams, state diagrams, ER diagrams, Gantt charts,
pie charts, git graphs, and more.

---

## Requirements

- Python 3.9+
- `quickjs-ng`, `resvg_py` (installed automatically)
- No system packages, no Node.js, no npm, no browser

---

## Testing

```bash
pip install -e ".[test]"
pytest tests/ -v
```

---

## Contributing

1. Fork and create a feature branch
2. Add tests for new functionality
3. Run `pytest tests/` — all must pass
4. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">
Made by <a href="https://github.com/MohammadRaziei">Mohammad Raziei</a>
</div>
