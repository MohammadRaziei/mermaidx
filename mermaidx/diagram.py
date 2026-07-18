"""
mermaidx.diagram — the object returned by mermaidx.render().

    DiagramBase   -- all the shared machinery: caching, and default
                     implementations of every derived output (png/raw/
                     numpy/pdf/ascii/save), each computed from self.svg().
    Diagram       -- backend='quickjs' (default) or 'v8': mermaid.js running
                     inside QuickJS-ng or real V8.
    DiagramRust   -- any backend from the optional `mmdr` package (e.g.
                     'merman', 'mermaid-rs-renderer'): svg() delegates to
                     mmdr, but png/raw/numpy/pdf still go through *our*
                     resvg + hand-written PDF writer -- so backends that
                     don't natively support e.g. PDF (mmdr's own
                     Diagram.pdf() raises NotImplementedError) get it here
                     for free.

Every public method (svg/png/raw/numpy/pdf/ascii) is lazy *and* cached:
nothing is computed until you call it, and calling it again with the same
arguments returns the memoized result instead of recomputing. Caching
itself lives entirely in DiagramBase; subclasses never have to think about
it -- they only override the private `_svg()`/`_png()`/... hooks that
actually compute a value. A subclass that wants a different (e.g. native)
way to produce PNGs can override just `_png()` and still get caching, save(),
and everything else for free.
"""

from __future__ import annotations

import atexit
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from mermaidx.ascii import render_ascii
from mermaidx.engines.quickjs_engine import Engine as _QuickJSEngine
from mermaidx.engines.quickjs_engine import MermaidRenderError as _QuickJSRenderError
from mermaidx.pdf_writer import png_to_pdf
from mermaidx.png_decode import decode_png_rgba, decode_png
from mermaidx.raster import render_png

try:
    from mermaidx.engines.v8_engine import Engine as _V8Engine
    from mermaidx.engines.v8_engine import MermaidRenderError as _V8RenderError
    _V8_AVAILABLE = True
except ImportError:
    _V8_AVAILABLE = False

if TYPE_CHECKING:
    import numpy as np

# One persistent, lazily-started engine per *name* ("quickjs" / "v8"), shared
# by every render() call in the process -- loading mermaid.js (~6MB of
# source) is the expensive part, so each engine only pays that cost once,
# and both can coexist if a caller explicitly asks for each by name (e.g.
# `backend="quickjs"` for one render, `backend="v8"` for another). Engine
# instances are synchronous by design -- start()/render_svg() already block
# internally on their own dedicated worker thread, so no asyncio is needed
# here at all.
_engines: dict = {}
_engines_lock = threading.Lock()


def _get_engine_by_name(name: str):
    """
    Lazily creates and caches one engine instance per name ("quickjs" or
    "v8"), so both can coexist in the same process without one evicting
    the other.
    """
    if name not in _engines:
        with _engines_lock:
            if name not in _engines:  # re-check inside the lock
                if name == "quickjs":
                    e = _QuickJSEngine()
                elif name == "v8":
                    if not _V8_AVAILABLE:
                        raise ImportError(
                            "backend='v8' requires the optional 'mini-racer' package. "
                            "Install it with:\n    pip install mermaidx[v8]"
                        )
                    e = _V8Engine()
                else:
                    raise ValueError(f"Unknown JS engine {name!r}; expected 'quickjs' or 'v8'.")
                e.start()
                # Some engine backends (e.g. engines.v8_engine, built on
                # py_mini_racer) have background threads that don't join
                # cleanly if the process exits without closing them first --
                # register a clean shutdown so callers never have to think
                # about this themselves.
                atexit.register(e.close)
                _engines[name] = e
    return _engines[name]


_MISSING = object()


class DiagramBase:
    """
    Shared machinery for every backend.

    Subclasses override the private, *uncached* `_svg()` / `_png()` /
    `_raw()` / `_numpy()` / `_pdf()` / `_ascii()` hooks; the public methods
    of the same name (without the underscore) add caching on top and are
    defined here exactly once. Most subclasses only need to override
    `_svg()` -- the default `_png()`/`_raw()`/`_numpy()`/`_pdf()` all just
    rasterize `self.svg()` via resvg, which is enough to make every output
    format available regardless of backend.

    Not instantiated directly -- use mermaidx.render(), which picks the right
    subclass for the requested backend.
    """

    backend: str = "base"

    def __init__(self, source: str, **opts) -> None:
        self._source = source
        self._opts = opts
        self._cache: dict = {}

    # ------------------------------------------------------------------
    # memoization helper -- keyed by (method name, sorted kwargs)
    # ------------------------------------------------------------------

    def _cached(self, name: str, kwargs: dict, compute):
        key = (name, tuple(sorted(kwargs.items())))
        result = self._cache.get(key, _MISSING)
        if result is _MISSING:
            result = compute()
            self._cache[key] = result
        return result

    # ------------------------------------------------------------------
    # SVG
    # ------------------------------------------------------------------

    def _svg(self) -> str:
        """Uncached SVG computation. Subclasses must override this."""
        raise NotImplementedError

    def svg(self) -> str:
        """Return the diagram as an SVG string (computed once, then cached)."""
        return self._cached("svg", {}, self._svg)

    # ------------------------------------------------------------------
    # PNG
    # ------------------------------------------------------------------

    def _png(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> bytes:
        """Uncached PNG computation. Default: rasterize self.svg() via
        resvg. Override in a subclass for a different (e.g. native) path."""
        kwargs = dict(background=background, width=width, height=height)
        if width is None and height is None and scale is not None:
            kwargs["scale"] = scale
        return render_png(self.svg(), **kwargs)

    def png(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> bytes:
        """Return the diagram as PNG bytes.

        Args:
            width:      Canvas width hint in pixels.
            height:     Canvas height hint in pixels.
            scale:      Size multiplier, used only if width/height are both omitted
                        (e.g. scale=2.0 for a "2x" render at the diagram's natural size).
            background: CSS color, e.g. ``"#ffffff"``. Transparent by default.

        Note:
            Aspect ratio is always preserved (like most SVG rasterizers).
            If both width and height are given, width wins and height is
            derived from it -- this never stretches the diagram.
        """
        kwargs = dict(width=width, height=height, scale=scale, background=background)
        return self._cached("png", kwargs, lambda: self._png(**kwargs))

    # ------------------------------------------------------------------
    # Raw RGBA / numpy
    # ------------------------------------------------------------------

    def _raw(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> tuple[bytes, int, int]:
        png_bytes = self.png(width=width, height=height, scale=scale, background=background)
        return decode_png_rgba(png_bytes)

    def raw(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> tuple[bytes, int, int]:
        """Return raw RGBA8888 pixels as ``(bytes, width, height)`` — no
        imaging library involved, just resvg's output decoded directly."""
        kwargs = dict(width=width, height=height, scale=scale, background=background)
        return self._cached("raw", kwargs, lambda: self._raw(**kwargs))

    def _numpy(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> "np.ndarray":
        import numpy as np  # already validated present by numpy() below
        raw, w, h = self.raw(width=width, height=height, scale=scale, background=background)
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)

    def numpy(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> "np.ndarray":
        """Return an ``(H, W, 4)`` uint8 RGBA array. Requires ``numpy``."""
        try:
            import numpy  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "numpy is required for .numpy(). Install it with:\n"
                "    pip install numpy"
            ) from exc
        kwargs = dict(width=width, height=height, scale=scale, background=background)
        return self._cached("numpy", kwargs, lambda: self._numpy(**kwargs))

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------

    def _pdf(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: float = 1.0,
        background: Optional[str] = None,
        pdf_format: Optional[str] = None,
        pdf_landscape: bool = False,
        pdf_margin: str = "0",
    ) -> bytes:
        render_kwargs = dict(background=background, width=width, height=height)
        if width is None and height is None:
            render_kwargs["scale"] = scale
        png_bytes = render_png(self.svg(), **render_kwargs)
        decoded = decode_png(png_bytes)
        return png_to_pdf(
            decoded, pdf_format=pdf_format, landscape=pdf_landscape,
            margin=pdf_margin, scale=1.0, background_color=background,
        )

    def pdf(
        self,
        *,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: float = 1.0,
        background: Optional[str] = None,
        pdf_format: Optional[str] = None,
        pdf_landscape: bool = False,
        pdf_margin: str = "0",
    ) -> bytes:
        """Return the diagram as PDF bytes (fully supported on every backend
        — no imaging library needed either: a hand-written, dependency-free
        PDF writer embeds the resvg-rendered pixels directly).

        Args:
            width, height: Canvas size in pixels (only when pdf_format is None --
                            with a fixed pdf_format the paper size wins instead).
            scale:         Resolution multiplier, used if width/height are omitted
                           (only when pdf_format is None).
            background:    CSS color for the page background.
            pdf_format:    Paper format e.g. ``"A4"``, ``"Letter"``. None = fit to diagram.
            pdf_landscape: Landscape orientation.
            pdf_margin:    CSS-style margin e.g. ``"1cm"`` (only with pdf_format).
        """
        kwargs = dict(width=width, height=height, scale=scale, background=background,
                      pdf_format=pdf_format, pdf_landscape=pdf_landscape, pdf_margin=pdf_margin)
        return self._cached("pdf", kwargs, lambda: self._pdf(**kwargs))

    # ------------------------------------------------------------------
    # ASCII
    # ------------------------------------------------------------------

    def _ascii(self, **opts) -> str:
        return render_ascii(self._source, **opts)

    def ascii(self, **opts) -> str:
        """Return the diagram as ASCII/Unicode box-drawing art (via termaid).

        Rendered straight from the Mermaid source (termaid has its own
        parser -- it doesn't go through the SVG at all, or care which
        backend produced it), so it's available even if .svg() was never
        called.
        """
        return self._cached("ascii", opts, lambda: self._ascii(**opts))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    _EXTENSION_FORMATS = {".svg": "svg", ".png": "png", ".pdf": "pdf",
                          ".txt": "ascii", ".ascii": "ascii"}

    def save(
        self,
        output: str,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
        format: Optional[str] = None,
        **format_opts,
    ) -> None:
        """Save the diagram to *output*.

        Args:
            format: Force the output format ("svg", "png", "pdf", or "ascii")
                    regardless of the file extension. If omitted (the
                    default), the format is inferred from *output*'s
                    extension: ``.svg``, ``.png``, ``.pdf``, or ``.txt``/``.ascii``.
            **format_opts: Forwarded to the matching method -- pdf_format/
                    pdf_landscape/pdf_margin for "pdf", any termaid option for "ascii".

        Raises:
            ValueError: if the format can't be determined, or is unrecognised.
        """
        path = Path(output)
        fmt = format or self._EXTENSION_FORMATS.get(path.suffix.lower())
        if fmt is None:
            raise ValueError(
                f"Cannot infer output format from {output!r}. "
                "Pass format=\"svg\"/\"png\"/\"pdf\"/\"ascii\" explicitly, "
                "or use one of these extensions: "
                f"{sorted(set(self._EXTENSION_FORMATS))}"
            )

        if fmt == "svg":
            path.write_text(self.svg(), encoding="utf-8")
        elif fmt == "png":
            path.write_bytes(self.png(width=width, height=height, scale=scale, background=background))
        elif fmt == "pdf":
            path.write_bytes(self.pdf(
                width=width, height=height, scale=scale or 1.0,
                background=background, **format_opts,
            ))
        elif fmt == "ascii":
            path.write_text(self.ascii(**format_opts), encoding="utf-8")
        else:
            raise ValueError(
                f"Unknown format {fmt!r}. Supported: svg, png, pdf, ascii"
            )

    # ------------------------------------------------------------------
    # Jupyter / IPython display
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Display the diagram in a Jupyter/IPython cell (like `plt.show()`).

        Typing a Diagram as a cell's last expression already displays it
        automatically (via `_repr_svg_`) -- `.show()` is for when you want
        to display it explicitly instead (e.g. inside a loop).

        Displays exactly what `.svg()` returns -- whichever backend
        produced it -- so what you see is always the actual output of this
        package's own render pipeline, not a separate re-render through
        some other engine.
        """
        try:
            from IPython.display import SVG, display
        except ImportError as exc:
            raise ImportError(
                "show() needs IPython (you're not in a Jupyter/IPython session?). "
                "Install it with:\n    pip install ipython"
            ) from exc
        display(SVG(self.svg()))

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        first_line = (self._source.strip().splitlines() or [""])[0]
        return f"<{type(self).__name__} backend={self.backend!r} {first_line!r}>"

    def _repr_svg_(self) -> str:
        """Jupyter/IPython rich display — renders inline SVG automatically."""
        return self.svg()


class Diagram(DiagramBase):
    """mermaid.js v11 running inside a JS engine, with resvg (using a bundled
    font shared with the layout step) for everything downstream of SVG. See
    DiagramBase for the full method list.

    `backend` picks *which* JS engine runs mermaid.js -- both always render
    the exact same mermaid.js and produce byte-identical SVG output:

      - 'quickjs' (default): QuickJS-ng. Always available (mermaidx's one
        hard dependency), handles every diagram type mermaidx supports.
      - 'v8': real V8 via the optional `mini-racer` package -- noticeably
        faster (a real JIT vs. QuickJS-ng's interpreter-only execution; see
        the project's own benchmarks), at two costs: it's an extra install
        (`pip install mermaidx[v8]`), and it can't render `mindmap`
        diagrams (see engines/v8_engine.py's "Known limitation" docstring
        for why) -- use the default 'quickjs' for those.

    Example::

        import mermaidx

        d = mermaidx.render("flowchart LR; A-->B-->C")
        d2 = mermaidx.render("flowchart LR; A-->B-->C", backend="v8")

        d.svg()                          # str -- computed on first call
        d.svg() is d.svg()               # True -- cached, not recomputed
        d.png()                          # bytes (PNG)
        d.png(width=1200, background="#ffffff")   # a different cache entry
        d.raw()                          # (bytes, width, height) — RGBA8888
        d.numpy()                        # np.ndarray, no Pillow needed
        d.ascii()                        # ASCII/Unicode box-drawing art
        d.save("out.svg")
        d.save("out.png", width=1200)
        d.save("out.pdf", pdf_format="A4", pdf_margin="1cm")
        d.save("out.png.bak", format="png")   # force format regardless of extension
    """

    def __init__(
        self,
        source: str,
        backend: str = "quickjs",
        *,
        theme: Optional[str] = None,
        config: Optional[dict] = None,
        css: Optional[str] = None,
        **_ignored,
    ) -> None:
        if backend not in ("quickjs", "v8"):
            raise ValueError(f"Unknown backend {backend!r} for Diagram; expected 'quickjs' or 'v8'.")
        super().__init__(source, theme=theme, config=config, css=css)
        self.backend = backend
        self._theme = theme
        self._config = config
        self._css = css

    def _svg(self) -> str:
        engine = _get_engine_by_name(self.backend)  # raises ImportError first if backend="v8" but unavailable
        render_error = _QuickJSRenderError if self.backend == "quickjs" else _V8RenderError
        try:
            return engine.render_svg(self._source, self._theme or "default", self._config, self._css)
        except render_error as e:
            raise RuntimeError(f"Mermaid rendering failed: {e}") from e


class DiagramRust(DiagramBase):
    """Any backend provided by the optional `mmdr` package (e.g. 'merman',
    'mermaid-rs-renderer' -- see mermaidx.backends()). Only _svg() is delegated
    to mmdr; png/raw/numpy/pdf all go through *our* resvg + PDF writer
    instead of mmdr's own, which means outputs mmdr doesn't natively
    support (its own Diagram.pdf() currently raises NotImplementedError)
    work here anyway. The trade-off: rasterization fidelity is resvg's, not
    mmdr's own Rust rasterizer -- only the SVG (i.e. the actual layout)
    comes from mmdr.
    """

    def __init__(self, source: str, backend: str, **opts) -> None:
        super().__init__(source, **opts)
        self.backend = backend

    def _svg(self) -> str:
        import mmdr
        return mmdr.render(self._source, backend=self.backend, **self._opts).svg()


def render(source: str, backend: Optional[str] = None, **opts) -> "DiagramBase":
    """
    Render a Mermaid diagram.

    Args:
        source:  Mermaid source text.
        backend: ``'quickjs'`` (default -- mermaidx's one hard dependency,
                 always available) or ``'v8'`` (faster, optional -- raises
                 ``ImportError`` with an install hint if the ``mini-racer``
                 package isn't present; can't render ``mindmap`` diagrams,
                 see ``Diagram``'s docstring). If the optional ``mmdr``
                 package is installed, also ``'merman'`` /
                 ``'mermaid-rs-renderer'``.
        **opts:  Forwarded to the chosen backend.
                 'quickjs' / 'v8': theme, config, css
                 mmdr backends: theme, node_spacing, rank_spacing, aspect_ratio

    Returns:
        A DiagramBase subclass instance (Diagram for 'quickjs'/'v8',
        DiagramRust for anything from mmdr). Every method
        (svg/png/raw/numpy/pdf/ascii) is lazy and cached, regardless of
        backend.
    """
    if backend in (None, "quickjs", "v8"):
        return Diagram(source, backend=backend or "quickjs", **opts)

    from .backends import backends

    try:
        import mmdr
    except ImportError as exc:
        raise ImportError(
            f"backend={backend!r} requires the optional 'mmdr' package. "
            "Install it with:\n    pip install mermaidx[rust]"
        ) from exc

    if backend not in mmdr.backends():
        raise ValueError(f"Unknown backend {backend!r}. Available: {backends()!r}")
    return DiagramRust(source, backend, **opts)
