# Export the main converter class
from .__about__ import __version__
from .mmdc import MermaidConverter, to_svg, to_png, to_pdf, convert
from .diagram import Diagram
from .raster import svg_to_png, svg_to_raw


def backends() -> list:
    """
    Available rendering backends.

    Always includes ``'js'`` (this package's own QuickJS + resvg engine,
    zero extra dependencies). If the optional ``mmdr`` package
    (https://github.com/mohammadraziei/mmdr) is installed — e.g. via
    ``pip install mmdc[rust]`` — its backends are appended too::

        >>> backends()
        ['js']                                       # mmdr not installed
        ['js', 'merman', 'mermaid-rs-renderer']       # mmdr installed
    """
    result = ["js"]
    try:
        import mmdr
    except ImportError:
        return result
    return result + list(mmdr.backends())


def render(source: str, backend: str = None, **opts):
    """
    Render a Mermaid diagram.

    Args:
        source:  Mermaid source text.
        backend: ``'js'`` (default — this package's own engine, always
                 available) or, if the optional ``mmdr`` package is
                 installed, ``'merman'`` / ``'mermaid-rs-renderer'``.
        **opts:  Forwarded to the chosen backend.
                 'js': theme, config, css
                 mmdr backends: theme, node_spacing, rank_spacing, aspect_ratio

    Returns:
        A Diagram — SVG is rendered immediately; PNG/raw/numpy/PDF are
        computed lazily from it on demand. When delegating to an ``mmdr``
        backend, this returns *mmdr's own* ``Diagram`` object directly: its
        API is identical (same reason we designed ours to match it), so no
        wrapping is needed.
    """
    if backend in (None, "js"):
        return Diagram(source, **opts)

    try:
        import mmdr
    except ImportError as exc:
        raise ImportError(
            f"backend={backend!r} requires the optional 'mmdr' package. "
            "Install it with:\n    pip install mmdc[rust]"
        ) from exc

    if backend not in mmdr.backends():
        raise ValueError(
            f"Unknown backend {backend!r}. Available: {backends()!r}"
        )
    return mmdr.render(source, backend=backend, **opts)


__all__ = [
    "__version__",
    # simple, synchronous, mmdr-compatible API (recommended)
    "render",
    "Diagram",
    "backends",
    "svg_to_png",
    "svg_to_raw",
    # persistent-session async API (for servers / batch rendering)
    "MermaidConverter",
    "to_svg",
    "to_png",
    "to_pdf",
    "convert",
]
