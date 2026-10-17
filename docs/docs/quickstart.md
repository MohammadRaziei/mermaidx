---
title: Quick start
sidebar_position: 2
description: Render your first diagram from Python, the command line or Jupyter.
---

## From Python

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
d.save("diagram.jpg", quality=90)       # also .jpeg, .bmp and .tga
d.save("diagram.pdf", pdf_format="A4")
print(d.ascii())
```

`render()` returns a `Diagram`. The SVG is computed once and cached, and every other format is derived from it.

```python
d.svg()                                  # str
d.png(width=1200, background="#ffffff")  # bytes
d.raw()                                  # (bytes, width, height), RGBA8888
d.numpy()                                # numpy array, needs numpy
d.pdf()                                  # bytes
```

## Render many diagrams

`render_many` uses a process pool, so it scales across CPU cores:

```python
diagrams = mermaidx.render_many([src1, src2, src3], workers=4, theme="dark")
for d, name in zip(diagrams, ["a.svg", "b.svg", "c.svg"]):
    d.save(name)
```

## From the command line

```bash
mermaidx -i diagram.mermaid -o diagram.svg
mermaidx -i diagram.mermaid -o diagram.png --scale 2.0
cat diagram.mermaid | mermaidx -i - -o diagram.pdf
```

The full list of options is on the [command line](./cli.md) page.

## In Jupyter

A `Diagram` displays itself when it is the last expression in a cell, the same way a DataFrame or a Matplotlib figure does:

```python
mermaidx.render("flowchart LR; A-->B-->C")
```

Try it in [Google Colab](https://colab.research.google.com/github/mohammadraziei/mermaidx/blob/master/examples/jupyter_demo.ipynb).

## Choose a backend

Pass `backend=` to use another engine. Each backend is described on the [backends](./backends.md) page.

```python
mermaidx.render("flowchart LR; A-->B", backend="v8")
```
