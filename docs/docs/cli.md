---
title: Command line
sidebar_position: 3
description: Every option of the mermaidx command.
---

```bash
mermaidx -i INPUT -o OUTPUT [options]
```

Without `-o`, or with `-o -`, the diagram is written to standard output. Use `-i -` to read the diagram from standard input.

The output format comes from the extension of `-o`: `.svg`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tga` or `.pdf`. Standard output has no extension, so it is SVG unless you pick another format with `-f`. `-f` also overrides the extension of a file, and names the format of a file that has none.

| Option | Description |
| --- | --- |
| `-i`, `--input FILE` | Mermaid source file, or `-` for standard input |
| `-o`, `--output FILE` | Output file, or `-` for standard output. Omit it to write to standard output too |
| `--data-uri` | Write the output to standard output as a data URI (`data:image/png;base64,...`) instead of raw bytes. Stdout only |
| `-f`, `--format FORMAT` | Output format: `svg`, `png`, `jpg`, `jpeg`, `bmp`, `tga` or `pdf`. Overrides the extension of `-o`; the default is that extension, or `svg` for standard output |
| `--backend KIND:NAME` | Rendering backend, such as `js:mermaid` (the default), `js:pele` or `rust:merman` |
| `--engine NAME` | JS engine of a `js:` backend, `quickjs` (the default) or `v8` |
| `--list-backends` | List the available backends and engines, and exit |
| `-w`, `--width N` | Output width in pixels (PNG, and PDF when fitting) |
| `-H`, `--height N` | Output height in pixels |
| `--scale N` | Size multiplier, used when `-w` and `-H` are omitted |
| `-t`, `--theme NAME` | A Mermaid theme: `default`, `base`, `dark`, `forest`, `neutral`, `neo`, `neo-dark`, `redux`, `redux-dark`, `redux-color`, `redux-dark-color` or `null`. Omit it to let Mermaid pick a theme for each diagram type, like `mmdc` |
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
mermaidx -i flow.mmd --engine v8 -o flow.svg
mermaidx -i flow.mmd --backend js:pele -o flow.png
mermaidx -i flow.mmd -f png -o - > flow.png     # PNG on standard output
cat flow.mmd | mermaidx -i - -f pdf | lpr       # pipe a PDF to another program
mermaidx -i flow.mmd -o flow -f jpg             # a file name without an extension
mermaidx -i flow.mmd -f png --data-uri          # data:image/png;base64,... for HTML, Markdown or JSON
```

Binary formats go to standard output as raw bytes, so they can be redirected or piped. If standard output is a terminal, mermaidx refuses to print them and says so; redirect (`> flow.png`) or pass `--data-uri` to get the same image as text. The MIME type is `image/svg+xml`, `image/png`, `image/jpeg`, `image/bmp`, `image/x-tga` or `application/pdf`; browsers do not display TGA at all, and many block a PDF opened from a data URI.
