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

    mermaidx.render(src, backend="js:pele")     # backends: 'js:mermaid' (default), 'js:pele', 'rust:<name>'
    mermaidx.render(src, engine="v8")          # JS engine for js: backends: 'quickjs' (default) or 'v8'
    mermaidx.backends()          # ['js:mermaid', 'js:pele']  (+ 'rust:...' if mmdr is installed)
    mermaidx.available_engines() # ['quickjs']  (+ 'v8' if mini-racer is installed)
    mermaidx.render_many(sources, workers=4)   # real parallelism (multiprocessing)
    mermaidx.shutdown_pool()     # stop the workers render_many() keeps between calls
"""

from .__about__ import __version__
from .diagram import Diagram, DiagramBase, DiagramRust, render
from .backends import available_engines, backends
from .raster import svg_to_png, svg_to_jpg, svg_to_image, svg_to_raw
from .pool import render_many, shutdown_pool

__all__ = [
    "__version__",
    "render",
    "Diagram",
    "DiagramBase",
    "DiagramRust",
    "backends",
    "available_engines",
    "svg_to_png",
    "svg_to_jpg",
    "svg_to_image",
    "svg_to_raw",
    "render_many",
    "shutdown_pool",
]
