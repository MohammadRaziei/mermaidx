"""
mmdc — Mermaid diagram rendering, no browser, Node.js, or npm required.

    import mmdc

    d = mmdc.render("flowchart LR; A-->B-->C")   # SVG rendered immediately
    d.svg()                                        # str
    d.png()                                        # bytes
    d.png(width=1200, background="#ffffff")
    d.raw()                                        # (bytes, w, h) RGBA8888
    d.numpy()                                      # np.ndarray, no Pillow needed
    d.pdf()                                         # bytes -- fully supported
    d.save("out.svg") / d.save("out.png") / d.save("out.pdf")

    mmdc.backends()          # ['js']  (+ mmdr's backends if installed)
    mmdc.render_many(sources, workers=4)   # real parallelism (multiprocessing)
    mmdc.render_ascii(source)              # terminal-friendly text, needs mmdc[ascii]
"""

from .__about__ import __version__
from .diagram import Diagram, render
from .backends import backends
from .raster import svg_to_png, svg_to_raw
from .pool import render_many
from .ascii import render_ascii

__all__ = [
    "__version__",
    "render",
    "Diagram",
    "backends",
    "svg_to_png",
    "svg_to_raw",
    "render_many",
    "render_ascii",
]
