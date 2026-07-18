"""
mermaidx — Mermaid diagram rendering, no browser, Node.js, or npm required.

    import mermaidx

    d = mermaidx.render("flowchart LR; A-->B-->C")   # SVG rendered immediately
    d.svg()                                        # str
    d.png()                                        # bytes
    d.png(width=1200, background="#ffffff")
    d.raw()                                        # (bytes, w, h) RGBA8888
    d.numpy()                                      # np.ndarray, no Pillow needed
    d.pdf()                                         # bytes -- fully supported
    d.save("out.svg") / d.save("out.png") / d.save("out.pdf")

    mermaidx.backends()          # ['quickjs']  (+ 'v8'/mmdr's backends if installed)
    mermaidx.render_many(sources, workers=4)   # real parallelism (multiprocessing)
    mermaidx.render_ascii(source)              # terminal-friendly text (always available)
"""

from .__about__ import __version__
from .diagram import Diagram, DiagramBase, DiagramRust, render
from .backends import backends
from .raster import svg_to_png, svg_to_raw
from .pool import render_many
from .ascii import render_ascii

__all__ = [
    "__version__",
    "render",
    "Diagram",
    "DiagramBase",
    "DiagramRust",
    "backends",
    "svg_to_png",
    "svg_to_raw",
    "render_many",
    "render_ascii",
]
