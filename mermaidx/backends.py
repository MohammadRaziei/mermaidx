"""mermaidx.backends — which rendering backends are available."""

from __future__ import annotations


def backends() -> list:
    """
    Available rendering backends.

    Always includes ``'quickjs'`` (mermaidx's one hard dependency, always
    available). If the optional ``mini-racer`` package is installed
    (``pip install mermaidx[v8]``), also ``'v8'`` (faster, real JIT --
    can't render ``mindmap`` diagrams, see ``Diagram``'s docstring). If the
    optional ``mmdr`` package (https://github.com/mohammadraziei/mmdr) is
    installed -- e.g. via ``pip install mermaidx[rust]`` -- its backends are
    appended too::

        >>> backends()
        ['quickjs']                                    # nothing extra installed
        ['quickjs', 'v8']                               # mermaidx[v8] installed
        ['quickjs', 'merman', 'mermaid-rs-renderer']     # mermaidx[rust] installed
        ['quickjs', 'v8', 'merman', 'mermaid-rs-renderer']  # both installed
    """
    result = ["quickjs"]
    try:
        import py_mini_racer  # noqa: F401
        result.append("v8")
    except ImportError:
        pass
    try:
        import mmdr
    except ImportError:
        return result
    return result + list(mmdr.backends())
