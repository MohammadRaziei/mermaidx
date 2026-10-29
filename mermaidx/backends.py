"""
mermaidx.backends -- the backend naming scheme, and which backends/engines are available.

A *backend* is what turns Mermaid text into an SVG. Its name is ``'<kind>:<name>'``:

    js:mermaid   mermaid.js (the reference implementation; the default)
    js:pele      pele (https://pele.run): small, synchronous, its own layout, themed by CSS variables
    rust:<name>  a backend of the optional `mmdr` package, e.g. ``rust:merman``

The ``js:`` backends run inside a JS *engine*, picked with the separate ``engine=`` parameter:

    quickjs      QuickJS-ng (the default for every js: backend; always available)
    v8           real V8 via the optional `mini-racer` package (faster, a JIT)

``engine`` is ``None`` unless the caller sets it: ``None`` means ``'quickjs'`` for a ``js:`` backend, and is the
only value a ``rust:`` backend accepts (they have no JS engine).
"""

from __future__ import annotations

from typing import Optional

DEFAULT_BACKEND = "js:mermaid"
DEFAULT_ENGINE = "quickjs"
JS_ENGINES = ("quickjs", "v8")
JS_BACKENDS = ("js:mermaid", "js:pele")


def available_engines() -> list:
    """
    The JS engines the ``js:`` backends can run in.

    Always includes ``'quickjs'`` (mermaidx's one hard dependency). If the optional ``mini-racer`` package is
    installed (``pip install mermaidx[v8engine]``), also ``'v8'``::

        >>> available_engines()
        ['quickjs']           # nothing extra installed
        ['quickjs', 'v8']     # mermaidx[v8engine] installed
    """
    result = ["quickjs"]
    try:
        import py_mini_racer  # noqa: F401
        result.append("v8")
    except ImportError:
        pass
    return result


def backends() -> list:
    """
    Available rendering backends, as ``'<kind>:<name>'``.

    Always includes ``'js:mermaid'`` and ``'js:pele'``. If the optional ``mmdr`` package
    (https://github.com/mohammadraziei/mmdr) is installed -- e.g. via ``pip install mermaidx[rust]`` -- its
    backends are appended too, with a ``rust:`` prefix::

        >>> backends()
        ['js:mermaid', 'js:pele']                                                  # nothing extra installed
        ['js:mermaid', 'js:pele', 'rust:merman', 'rust:mermaid-rs-renderer']       # mermaidx[rust] installed
    """
    result = list(JS_BACKENDS)
    try:
        import mmdr
    except ImportError:
        return result
    return result + [f"rust:{name}" for name in mmdr.backends()]


# What a pre-0.11 name became, for the error message (the names were bare: 'quickjs', 'v8', 'merman', ...).
_LEGACY_HINTS = {
    "quickjs": "backend='js:mermaid' (the default; engine='quickjs' is the default too)",
    "v8": "backend='js:mermaid', engine='v8'",
}


def parse_backend(backend: Optional[str]) -> tuple:
    """``'js:pele'`` -> ``('js', 'pele')``. ``None`` means the default backend, ``'js:mermaid'``.

    Raises ValueError for a name that is not ``'<kind>:<name>'`` (with a pointer to the new name for the bare
    names of earlier versions) or whose kind is neither ``js`` nor ``rust``. Whether the *name* exists is for
    the caller to check: only it knows what is installed."""
    if backend is None:
        backend = DEFAULT_BACKEND
    kind, sep, name = backend.partition(":")
    if not sep or not name:
        hint = _LEGACY_HINTS.get(backend) or f"backend='rust:{backend}' if it is a backend of the `mmdr` package"
        raise ValueError(
            f"Backend {backend!r} is not of the form '<kind>:<name>' (e.g. 'js:mermaid', 'js:pele', "
            f"'rust:merman'). Bare names were removed in 0.11 -- use {hint}."
        )
    if kind not in ("js", "rust"):
        raise ValueError(f"Unknown backend kind {kind!r} in {backend!r}; expected 'js' or 'rust'.")
    return kind, name


def resolve_engine(kind: str, engine: Optional[str]) -> Optional[str]:
    """The engine a backend of this kind runs in: ``'quickjs'`` for ``js`` unless the caller chose another,
    ``None`` for ``rust`` (which has no JS engine -- naming one is an error, not silently ignored)."""
    if kind == "rust":
        if engine is not None:
            raise ValueError(f"engine={engine!r} does not apply to a 'rust:' backend (it has no JS engine).")
        return None
    if engine is None:
        return DEFAULT_ENGINE
    if engine not in JS_ENGINES:
        raise ValueError(f"Unknown engine {engine!r}; expected one of {JS_ENGINES}.")
    return engine
