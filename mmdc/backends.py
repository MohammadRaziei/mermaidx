"""mmdc.backends — which rendering backends are available."""

from __future__ import annotations


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
