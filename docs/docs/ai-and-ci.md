---
title: AI agents and CI/CD
sidebar_position: 4
description: Why a browserless renderer of about 7 MB suits AI agents and CI pipelines, and how to check it.
---

Two kinds of machine are bad at "just start Chrome": the throwaway sandbox where an AI agent works, and the clean runner of a CI/CD pipeline. Both start from nothing, have no display, and pay for every megabyte they download. mermaidx was built for that situation: it draws Mermaid diagrams without a browser, and the whole install is about 7 MB.

## AI agents

An agent that writes documentation, a README or an architecture note often writes its diagrams as Mermaid text. To check the picture, or to hand it over as an image, something has to turn that text into SVG or PNG. With the official `mermaid-cli` that something is a headless Chrome (about 170 MB of Chromium) plus Node.js, which is a lot to ask of a fresh container.

With mermaidx an agent needs one step and no browser:

```bash
pip install mermaidx
```

That is the whole setup: no Chrome, no Puppeteer, no Node.js, no system packages and no compiler. Python 3.9 or newer is the only requirement, and the download is about 7 MB with its main dependencies ([check it yourself](#download-size)).

Rendering is one command or one call, and everything runs in the same process, so there is no server to start and no port to open:

```bash
mermaidx -i flow.mmd -o flow.png                  # file to file
cat flow.mmd | mermaidx -i - -f png -o - > flow.png   # text in, image out, through pipes
mermaidx -i flow.mmd -f png --data-uri            # the image as text, for JSON, Markdown or HTML
```

```python
import mermaidx

d = mermaidx.render("flowchart LR; A-->B-->C")
d.svg()    # str
d.png()    # bytes
```

A few details that matter when a program, not a person, reads the output:

- **Standard output carries only the diagram.** The `saved to ...` message goes to standard error, and `-q` hides it. See the [command line](./cli.md) page for every option.
- **Text or bytes, as you need them.** `svg()` is a string, `png()` and `pdf()` are bytes, `--data-uri` turns any format into a plain string.
- **Nothing is downloaded at render time.** The Python code of the base install makes no network calls (there is no `urllib`, `requests` or socket use in the package), and `mermaid.js`, `pele.js`, the ELK layout, ZenUML and the font all ship inside the wheel.

## CI/CD

A pipeline runner is usually clean on every run, so whatever the job needs is downloaded again unless you cache it. About 7 MB instead of a browser is the difference between a step you barely notice and one you start to cache and maintain.

The usual use is to keep the diagram source (`.mmd`) in the repository and render it at build time, so the image in the docs can never drift from the source:

```bash
pip install mermaidx
mermaidx -i docs/architecture.mmd -o docs/architecture.svg -q
mermaidx -i docs/architecture.mmd -o docs/architecture.pdf --pdf-format A4 -q
```

For many diagrams in one job, `render_many` spreads them over several processes; see [Quick start](./quickstart.md#render-many-diagrams).

mermaidx's own pipeline works this way:

- the [docs workflow](https://github.com/MohammadRaziei/mermaidx/blob/master/.github/workflows/docs.yml) runs on `ubuntu-latest` and renders the benchmark samples with every backend on each release;
- the test job of the [wheel workflow](https://github.com/MohammadRaziei/mermaidx/blob/master/.github/workflows/wheel.yml) runs on Ubuntu, macOS and Windows.

One thing to know before you compare against `mmdc`: mermaidx measures text with the bundled DejaVu Sans, so a diagram can differ from a real `mmdc` run on your machine by a fraction of a pixel in text width. See [Known issues](./known-issues.md).

## Download size

`pip install mermaidx` downloads about 7 MB, including its main dependencies. You can check it yourself:

```bash
uvx pip-size mermaidx
```
