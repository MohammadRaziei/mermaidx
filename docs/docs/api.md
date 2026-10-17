---
title: Python API
sidebar_position: 5
description: Functions and methods of the mermaidx package.
---

```python
import mermaidx
```

## Functions

### `render(source, backend=None, **opts)`

Render a Mermaid diagram and return a `Diagram`.

- `source`: the Mermaid text.
- `backend`: `"quickjs"` (default), `"v8"`, `"merman"` or `"mermaid-rs-renderer"`. A backend whose package is missing raises `ImportError` with an install hint.
- `theme`: `"default"`, `"forest"`, `"dark"` or `"neutral"`.
- `config`: a dict of Mermaid configuration (`quickjs` and `v8`).
- `css`: CSS text to inject (`quickjs` and `v8`).
- `node_spacing`, `rank_spacing`, `aspect_ratio`: layout options of the Rust backends.
- `raster`: the SVG rasterizer. Only `"novasvg"` is supported. `"resvg"` raises a `ValueError`.

### `render_many(sources, *, workers=None, **opts)`

Render a list of sources in parallel with a process pool and return the `Diagram` objects in the same order. `workers` defaults to the smaller of the number of sources and the CPU count. The other options are passed to every diagram.

### `render_ascii(source, **opts)`

Return the diagram as text with box-drawing characters, for terminals. It is always available.

### `backends()`

Return the names of the backends that can be used in this environment.

### `svg_to_png`, `svg_to_jpg`, `svg_to_image`, `svg_to_raw`

Rasterize an SVG string you already have. For example, `svg_to_png(svg, width=None, height=None, background=None)` returns PNG bytes, and `svg_to_jpg` adds `quality=90`. `svg_to_raw` returns `(bytes, width, height)` with RGBA8888 pixels.

## `Diagram`

Every method that produces output takes the same size options. When you give none, the diagram is rendered at its natural size.

| Option | Meaning |
| --- | --- |
| `width`, `height` | Output size in pixels |
| `scale` | Size multiplier, used when `width` and `height` are omitted |
| `background` | CSS color, transparent by default |

Results are cached per set of options, so calling `d.svg()` twice computes once.

| Method | Returns |
| --- | --- |
| `svg()` | The SVG as `str` |
| `png(width, height, scale, background)` | PNG `bytes` |
| `jpg(..., quality=90)` | JPEG `bytes`. White background by default |
| `bmp(...)`, `tga(...)` | BMP and TGA `bytes` |
| `raw(...)` | `(bytes, width, height)`, RGBA8888 |
| `numpy(...)` | `numpy.ndarray`, no Pillow needed |
| `pdf(*, width, height, scale=1.0, background, pdf_format, pdf_landscape=False, pdf_margin="0")` | PDF `bytes`. Fits the diagram unless `pdf_format` is given |
| `ascii(**opts)` | The diagram as text |
| `save(output, ..., format=None, **format_opts)` | Writes a file. The format comes from the extension, or from `format` |
| `show()` | Opens the diagram for viewing |

```python
d = mermaidx.render("flowchart LR; A-->B-->C")

d.save("out.png", width=1200)
d.save("out.jpg", quality=85)
d.save("out.pdf", pdf_format="A4", pdf_margin="1cm")
d.save("out.png.bak", format="png")      # force the format
```

In Jupyter, a `Diagram` renders itself as SVG when it is the last expression of a cell.
