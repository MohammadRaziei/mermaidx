# mermaidx — Mermaid Diagram Converter for Python

[![PyPI](https://img.shields.io/pypi/v/mermaidx.svg)](https://pypi.org/project/mermaidx)
[![Python](https://img.shields.io/pypi/pyversions/mermaidx.svg)](https://pypi.org/project/mermaidx)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/MohammadRaziei/mermaidx/actions/workflows/wheel.yml/badge.svg)](https://github.com/MohammadRaziei/mermaidx/actions/workflows/wheel.yml)
[![GitHub stars](https://img.shields.io/github/stars/MohammadRaziei/mermaidx?style=social)](https://github.com/MohammadRaziei/mermaidx/stargazers)

<div align="center">
<img src="https://raw.githubusercontent.com/MohammadRaziei/mermaidx/master/docs/static/img/logo.svg" width="150pt"/>
</div>

Convert Mermaid diagrams to SVG, PNG, PDF, or ASCII art — **fully offline and fast, just `pip install mermaidx`**.

**Completely browserless.** No Node.js, no npm, no Chrome, no system packages, nothing to compile. And because there's no browser to boot, `mermaidx` renders noticeably faster than the official `mermaid-cli`, which drives a real headless Chrome through Puppeteer for every single diagram — `mermaidx` uses a fast, embedded JS engine instead.

```bash
pip install mermaidx
```

That's it — SVG, PNG, PDF, and ASCII output all work out of the box; nothing else to install.

---

## Why mermaidx?

The official Mermaid CLI (`@mermaid-js/mermaid-cli`) works by spinning up a real headless Chrome via Puppeteer for every render. That works, but a full browser is slow to start and heavy to install (~170MB+ of Chromium), which shows up directly in wall-clock time — especially in CI pipelines rendering many diagrams, or anything short-lived like a serverless function.

`mermaidx` renders the actual, current Mermaid v11 JS library — not a reimplementation, not a subset — but runs it inside a small embedded JavaScript engine instead of a browser. No browser process to spawn, no page to load, no DOM to boot — just the JS engine running Mermaid's own layout code directly. That's the whole speed difference in one sentence: **browser vs. no browser.**

---

## Quick Start

```python
import mermaidx

d = mermaidx.render("""
graph TD
    A[Install] --> B[Import]
    B --> C[Convert]
    C --> D[Done]
""")

d.save("diagram.svg")
d.save("diagram.png", scale=2.0)
d.save("diagram.pdf", pdf_format="A4")
print(d.ascii())
```

```bash
mermaidx -i diagram.mermaid -o diagram.svg
mermaidx -i diagram.mermaid -o diagram.png --scale 2.0
cat diagram.mermaid | mermaidx -i - -o diagram.pdf
```

---

## Jupyter

A `Diagram` displays automatically as the last expression in a cell — no extra code needed, the same way a DataFrame or a matplotlib figure does:

```python
import mermaidx
mermaidx.render("flowchart LR; A-->B-->C")   # just shows up
```

`.show()` displays it explicitly (e.g. inside a loop) — it always shows exactly what `.svg()` returns, so what you see is this package's own render output, not a separate re-render through some other engine.

See [`examples/jupyter_demo.ipynb`](examples/jupyter_demo.ipynb) for a full walkthrough: display, PNG/PDF/ASCII export, themes, and batch rendering.

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
- **ASCII** — a completely separate, lightweight path via [termaid](https://pypi.org/project/termaid/) (pure Python, ~700KB, zero dependencies), which parses the Mermaid source itself rather than going through the SVG.

Rendering is CPU-bound, synchronous, single-process — there's no browser or subprocess to wait on, so there's nothing for `async` to usefully overlap. See [`mermaidx.render_many()`](#parallel-batch-rendering) below for real parallelism instead.

Every backend is a small subclass of one shared `DiagramBase` — `Diagram` for `'js'`, `DiagramRust` for anything from the optional `mmdr` package. Subclasses only override the private `_svg()` hook; the public, cached `svg()`/`png()`/`pdf()`/`raw()`/`numpy()`/`ascii()`/`save()` are all written once in the base class and work identically regardless of which backend produced the SVG.

---

## Python API

### `render(source, backend=None, **opts) -> Diagram`

```python
import mermaidx

d = mermaidx.render("flowchart LR; A-->B-->C")
```

`render()` itself does nothing but store the source — every `Diagram` method below is **lazy and cached**: nothing is computed until you call it, and calling it again with the same arguments returns the memoized result instead of recomputing.

| Method | Returns | Notes |
|---|---|---|
| `.svg()` | `str` | Computed on first call, cached after |
| `.png(width?, height?, scale?, background?)` | `bytes` | Aspect ratio always preserved |
| `.pdf(pdf_format?, pdf_landscape?, pdf_margin?, width?, height?, scale?, background?)` | `bytes` | `pdf_format=None` (default) fits the page to the diagram |
| `.ascii(**opts)` | `str` | Renders straight from the Mermaid source, doesn't need `.svg()` first |
| `.raw(width?, height?, background?)` | `(bytes, w, h)` | Raw RGBA8888, no imaging library involved |
| `.numpy(width?, height?, background?)` | `np.ndarray` | `(H, W, 4)` uint8; requires `numpy` |
| `.save(path, format=None, ...)` | `None` | Format from `format=`, or inferred from the extension otherwise |
| `._repr_svg_()` | `str` | Automatic inline rendering in Jupyter/IPython |

```python
d.svg() is d.svg()      # True -- second call is a cache hit, not a re-render
d.png(width=1200, background="#ffffff")
d.raw()                 # (bytes, width, height) -- RGBA8888
d.numpy()                # np.ndarray, no Pillow needed
d.ascii()                # ASCII/Unicode box-drawing art
d.save("out.pdf", pdf_format="A4", pdf_margin="1cm")
```

### `save()`: format from the extension, or forced explicitly

```python
d.save("out.svg")                       # -> svg
d.save("out.png")                       # -> png
d.save("out.pdf")                       # -> pdf
d.save("out.txt")                       # -> ascii
d.save("out.whatever", format="png")    # force a format regardless of extension
```

### Themes, config, CSS

```python
mermaidx.render(source, theme="dark")                    # "default" | "forest" | "dark" | "neutral"
mermaidx.render(source, config={"flowchart": {"curve": "basis"}})
mermaidx.render(source, css=".node rect { rx: 8; ry: 8; }")
```

### Parallel batch rendering

Rendering is pure CPU work — no I/O to overlap, so real concurrency means real processes, not `async`:

```python
diagrams = mermaidx.render_many(sources, workers=4, theme="dark")
for d, name in zip(diagrams, output_names):
    d.save(name)
```

Each worker process starts its own persistent engine once and reuses it for every diagram routed to it.

### ASCII / terminal output

Works out of the box — [termaid](https://pypi.org/project/termaid/) (pure Python, ~700KB, zero dependencies of its own) is a core dependency, not an optional extra:

```python
print(mermaidx.render_ascii("graph LR; A-->B-->C"))
# or, equivalently: mermaidx.render("graph LR; A-->B-->C").ascii()
```
```
┌───┐    ┌───┐    ┌───┐
│ A ├───►│ B ├───►│ C │
└───┘    └───┘    └───┘
```

### Low-level utilities

Rasterize any SVG string directly, without going through `render()`:

```python
from mermaidx import svg_to_png, svg_to_raw

svg = open("diagram.svg").read()
png = svg_to_png(svg, width=1200, background="#ffffff")
raw, w, h = svg_to_raw(svg)
```

### Additional backends (optional)

```bash
pip install mermaidx[rust]
```

If [`mmdr`](https://github.com/mohammadraziei/mmdr) (a native-Rust Mermaid renderer) is installed, its backends become available too — same interface either way, and with a bonus: PDF/raw/numpy work even for backends that don't natively support them (mmdr's own `Diagram.pdf()` raises `NotImplementedError`; `mermaidx`'s doesn't, for *any* backend), because every backend shares the same `DiagramBase` — only `svg()` differs per backend, everything downstream of it (PNG/PDF/raw/numpy) is the same resvg + PDF-writer pipeline for all of them:

```python
mermaidx.backends()
# ['js']                                   # mmdr not installed
# ['js', 'merman', 'mermaid-rs-renderer']   # mmdr installed

d = mermaidx.render(source, backend="merman")   # svg() comes from mmdr; everything else from mermaidx
d.pdf()                                      # works, even though mmdr's own .pdf() doesn't
```

---

## CLI

```bash
# SVG to stdout (no -o needed)
mermaidx -i diagram.mermaid
cat diagram.mermaid | mermaidx -i -

# save to file (format from extension)
mermaidx -i diagram.mermaid -o diagram.svg
mermaidx -i diagram.mermaid -o diagram.png
mermaidx -i diagram.mermaid -o diagram.pdf

# size
mermaidx -i diagram.mermaid -o diagram.png -w 1200
mermaidx -i diagram.mermaid -o diagram.png --scale 2.0

# theme & background
mermaidx -i diagram.mermaid -o diagram.svg --theme dark
mermaidx -i diagram.mermaid -o diagram.png --background "#f5f5f5"

# PDF options
mermaidx -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape --margin 1cm

# config & CSS
mermaidx -i diagram.mermaid -o diagram.svg --config config.json --css style.css

# info — Mermaid library version
mermaidx --info

# list available backends
mermaidx --list-backends

# pick a backend explicitly (requires mermaidx[rust] for anything but 'js')
mermaidx -i diagram.mermaid -o diagram.svg --backend merman

# version
mermaidx --version   # or -v
```

---

## Supported Diagram Types

Everything Mermaid v11 itself supports (this bundles the real library, not a subset):
flowcharts, sequence diagrams, class diagrams, state diagrams, ER diagrams, Gantt charts,
pie charts, git graphs, and more.

---

## Requirements

- Python 3.9+
- `quickjs-ng`, `resvg_py`, `termaid` (installed automatically)
- No system packages, no Node.js, no npm, no browser

---

## Testing

```bash
pip install -e ".[test]"
pytest tests/ -v
```

`tests/test_online_comparison.py` structurally cross-checks output against [mermaid.ink](https://mermaid.ink) (labels + aspect ratio, not pixel-diffing — two different rendering engines never match pixel-for-pixel). It needs outbound internet access and skips itself gracefully if that's unavailable or the service returns a transient error.

---

## History

- **mmdc, powered by [phasma](https://github.com/mohammadraziei/phasma)** — the original version of this project. It bundled a real (if small — around 20MB) headless browser, PhantomJS, and exposed an `async` Python API to match: rendering meant talking to a subprocess, so `async`/`await` genuinely mattered for concurrency.
- **0.6.x** — a full rewrite: PhantomJS's engine couldn't parse modern Mermaid (v11's ES2022+ syntax) at all, so the whole browser was replaced with mermaid.js running inside QuickJS-ng against a hand-written DOM/SVG shim, with resvg for rasterization. No subprocess left to wait on, so the API became synchronous. Three backends appeared: `js` (this engine), plus `merman` and `mermaid-rs-renderer` via the optional [`mmdr`](https://github.com/mohammadraziei/mmdr) package.
- **0.7.x, renamed to mermaidx** — same engine, new name. The old name, `mmdc`, was identical to the official Mermaid CLI's own binary name (`@mermaid-js/mermaid-cli` installs a command called `mmdc`) — a real collision, not just a branding concern. Renamed early, while it still could be.

---

## Acknowledgments

- [Mermaid](https://github.com/mermaid-js/mermaid) — the actual diagramming library this project renders. `mermaidx` wouldn't exist without it; all it does is run the real thing somewhere a browser can't go.
- [mmdr](https://github.com/mohammadraziei/mmdr) — a native-Rust Mermaid renderer by the same author, usable as an additional backend here (see [Additional backends](#additional-backends-optional)).
- [termaid](https://pypi.org/project/termaid/) — powers ASCII/Unicode terminal output.

---

## Contributing

1. Fork and create a feature branch
2. Add tests for new functionality
3. Run `pytest tests/` — all must pass
4. Open a pull request

---

## License

MIT — see [LICENSE](LICENSE) for details.

If `mermaidx` saves you from booting a headless Chrome instance a hundred times in CI, consider leaving a ⭐ on the repo — it genuinely helps others find the project.

---

<div align="center">
Made by <a href="https://github.com/MohammadRaziei">Mohammad Raziei</a>
</div>
