---
title: Command line
sidebar_position: 3
description: Every option of the mermaidx command.
---

```bash
mermaidx -i INPUT -o OUTPUT [options]
```

Without `-o`, the SVG is written to standard output. Use `-i -` to read the diagram from standard input.

The output format comes from the extension of `-o`: `.svg`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` or `.pdf`.

| Option | Description |
| --- | --- |
| `-i`, `--input FILE` | Mermaid source file, or `-` for standard input |
| `-o`, `--output FILE` | Output file. Omit it to write SVG to standard output |
| `--backend NAME` | Rendering backend, `quickjs` by default |
| `--list-backends` | List the available backends and exit |
| `-w`, `--width N` | Output width in pixels (PNG, and PDF when fitting) |
| `-H`, `--height N` | Output height in pixels |
| `--scale N` | Size multiplier, used when `-w` and `-H` are omitted |
| `-t`, `--theme NAME` | `default`, `forest`, `dark` or `neutral` |
| `-b`, `--background COLOR` | CSS background color, transparent by default |
| `-c`, `--config FILE` | Mermaid JSON config (`quickjs` and `v8` only) |
| `--css FILE` | CSS file to inject into the diagram (`quickjs` and `v8` only) |
| `--quality N` | JPEG quality from 1 to 100, 90 by default |
| `--pdf-format FORMAT` | Paper format such as `A4` or `Letter`; the default fits the diagram |
| `--landscape` | Landscape orientation, PDF only |
| `--margin MARGIN` | PDF margin such as `1cm`, 0 by default |
| `-q`, `--quiet` | Hide informational messages |
| `--info` | Print the Mermaid library version and exit |
| `--version`, `-v` | Print the mermaidx version and exit |

JPEG has no transparency, so the background is white unless you pass `-b`.

## Examples

```bash
mermaidx -i flow.mmd -o flow.png --scale 2 -b white
mermaidx -i flow.mmd -o flow.pdf --pdf-format A4 --margin 1cm
mermaidx -i flow.mmd -o flow.jpg --quality 80
mermaidx -i flow.mmd --backend v8 -o flow.svg
```
