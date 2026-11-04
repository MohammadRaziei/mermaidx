---
title: Python API
sidebar_position: 5
description: Functions and methods of the mermaidx package.
---

```python
import mermaidx
```

## Functions

### `render(source, backend=None, engine=None, **opts)`

Render a Mermaid diagram and return a `Diagram`.

- `source`: the Mermaid text.
- `backend`: what renders the diagram, named `<kind>:<name>`: `"js:mermaid"` (default), `"js:pele"`, `"rust:merman"` or `"rust:mermaid-rs-renderer"`. A backend whose package is missing raises `ImportError` with an install hint. A bare name such as `"quickjs"` raises `ValueError` that says which name replaces it.
- `engine`: the JS engine of a `js:` backend, `"quickjs"` or `"v8"`. `None` (the default) means `"quickjs"`. A `rust:` backend has no JS engine and raises `ValueError` if you pass one.
- `theme`: a Mermaid theme name: `"default"`, `"base"`, `"dark"`, `"forest"`, `"neutral"`, `"neo"`, `"neo-dark"`, `"redux"`, `"redux-dark"`, `"redux-color"`, `"redux-dark-color"` or `"null"`. `None` (the default) sends no theme, exactly as `mmdc` does, so Mermaid 12 gives each diagram type its own theme and look; pass `"default"` for the older, uniform look. `js:pele` has no themes: leave it unset, or `ValueError`.
- `config`: a dict of configuration (the `js:` backends).
- `css`: CSS text to inject (the `js:` backends). For `js:pele` it is added as a `<style>`, and is how you theme it, for example `svg{--pele-bg:#111}`.
- `node_spacing`, `rank_spacing`, `aspect_ratio`: layout options of the Rust backends.
- `raster`: the SVG rasterizer. Only `"novasvg"` is supported. `"resvg"` raises a `ValueError`.

### `render_many(sources, *, workers=None, **opts)`

Render a list of sources in parallel with a process pool and return the `Diagram` objects in the same order. `workers` defaults to the smaller of the number of sources and the CPU count. The other options are passed to every diagram.

### `backends()`

Return the names of the backends that can be used in this environment, as `<kind>:<name>`.

### `available_engines()`

Return the JS engines that can be used: `["quickjs"]`, plus `"v8"` when `mini-racer` is installed.

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
