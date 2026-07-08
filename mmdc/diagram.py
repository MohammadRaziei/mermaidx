"""
mmdc.diagram — the object returned by mmdc.render().

Mirrors the API of mmdr (https://github.com/mohammadraziei/mmdr) so the two
packages are interchangeable: same .svg()/.png()/.raw()/.numpy()/.save()
shape, same _repr_svg_() for notebooks. Unlike mmdr, SVG is rendered
*eagerly* in render() — Mermaid's own layout step has to run regardless of
which output format you ultimately want, so there's nothing meaningful to
defer there. PNG / raw / numpy / PDF conversions are computed lazily, only
when you actually call them, straight from the cached SVG via resvg.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from mmdc.engine import Engine, MermaidRenderError
from mmdc.pdf_writer import png_to_pdf
from mmdc.png_decode import decode_png_rgba, decode_png
from mmdc.raster import render_png

if TYPE_CHECKING:
    import numpy as np

# One persistent, lazily-started engine shared by every render() call in the
# process — loading mermaid.js (~6MB of source) is the expensive part, so it
# only happens once. Synchronous by design: Engine.start()/render_svg()
# already block internally on their own dedicated worker thread, so no
# asyncio is needed here at all.
_engine: Optional[Engine] = None
_engine_lock = threading.Lock()


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:  # re-check inside the lock
                e = Engine()
                e.start()
                _engine = e
    return _engine


class Diagram:
    """A rendered Mermaid diagram (the 'js' backend — see mmdc.render()).

    SVG is rendered immediately when the Diagram is created. Everything
    else (PNG, raw pixels, numpy, PDF) is derived from that cached SVG on
    demand.

    Example::

        import mmdc

        d = mmdc.render("flowchart LR; A-->B-->C")

        d.svg()                          # str (already computed)
        d.png()                          # bytes (PNG)
        d.png(width=1200, background="#ffffff")
        d.raw()                          # (bytes, width, height) — RGBA8888
        d.numpy()                        # np.ndarray, no Pillow needed
        d.save("out.svg")
        d.save("out.png", width=1200)
        d.save("out.pdf", pdf_format="A4", pdf_margin="1cm")
    """

    def __init__(
        self,
        source: str,
        *,
        theme: Optional[str] = None,
        config: Optional[dict] = None,
        css: Optional[str] = None,
        **_ignored,
    ) -> None:
        self._source = source
        self._theme = theme
        self._config = config
        self._css = css
        try:
            self._svg: str = _get_engine().render_svg(source, theme or "default", config, css)
        except MermaidRenderError as e:
            raise RuntimeError(f"Mermaid rendering failed: {e}") from e

    # ------------------------------------------------------------------
    # SVG — already computed
    # ------------------------------------------------------------------

    def svg(self) -> str:
        """Return the diagram as an SVG string (computed at render() time)."""
        return self._svg

    # ------------------------------------------------------------------
    # Rasterization — lazy, via resvg
    # ------------------------------------------------------------------

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
        kwargs = dict(background=background, width=width, height=height)
        if width is None and height is None and scale is not None:
            kwargs["scale"] = scale
        return render_png(self._svg, **kwargs)

    def raw(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> tuple[bytes, int, int]:
        """Return raw RGBA8888 pixels as ``(bytes, width, height)`` — no
        imaging library involved, just resvg's output decoded directly."""
        png_bytes = self.png(width=width, height=height, scale=scale, background=background)
        return decode_png_rgba(png_bytes)

    def numpy(
        self,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
    ) -> "np.ndarray":
        """Return an ``(H, W, 4)`` uint8 RGBA array. Requires ``numpy``."""
        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "numpy is required for .numpy(). Install it with:\n"
                "    pip install numpy"
            ) from exc
        raw, w, h = self.raw(width=width, height=height, scale=scale, background=background)
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)

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
        """Return the diagram as PDF bytes (fully supported — no imaging
        library needed here either: a hand-written, dependency-free PDF
        writer embeds the resvg-rendered pixels directly).

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
        render_kwargs = dict(background=background, width=width, height=height)
        if width is None and height is None:
            render_kwargs["scale"] = scale
        png_bytes = render_png(self._svg, **render_kwargs)
        decoded = decode_png(png_bytes)
        return png_to_pdf(
            decoded, pdf_format=pdf_format, landscape=pdf_landscape,
            margin=pdf_margin, scale=1.0, background_color=background,
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(
        self,
        output: str,
        width: Optional[float] = None,
        height: Optional[float] = None,
        scale: Optional[float] = None,
        background: Optional[str] = None,
        **pdf_opts,
    ) -> None:
        """Save the diagram to *output*, inferring the format from the extension.

        Raises:
            ValueError: if the file extension is not recognised.
        """
        path = Path(output)
        suffix = path.suffix.lower()

        if suffix == ".svg":
            path.write_text(self.svg(), encoding="utf-8")
        elif suffix == ".png":
            path.write_bytes(self.png(width=width, height=height, scale=scale, background=background))
        elif suffix == ".pdf":
            path.write_bytes(self.pdf(
                width=width, height=height, scale=scale or 1.0,
                background=background, **pdf_opts,
            ))
        else:
            raise ValueError(
                f"Cannot infer output format from {output!r}. "
                "Supported extensions: .svg  .png  .pdf"
            )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        first_line = (self._source.strip().splitlines() or [""])[0]
        return f"<Diagram backend='js' {first_line!r}>"

    def _repr_svg_(self) -> str:
        """Jupyter/IPython rich display — renders inline SVG automatically."""
        return self._svg


def render(source: str, backend: Optional[str] = None, **opts) -> "Diagram":
    """
    Render a Mermaid diagram.

    Args:
        source:  Mermaid source text.
        backend: ``'js'`` (default — this package's own QuickJS + resvg
                 engine, always available, zero extra dependencies) or, if
                 the optional ``mmdr`` package is installed,
                 ``'merman'`` / ``'mermaid-rs-renderer'``.
        **opts:  Forwarded to the chosen backend.
                 'js': theme, config, css
                 mmdr backends: theme, node_spacing, rank_spacing, aspect_ratio

    Returns:
        A Diagram. SVG is rendered immediately; PNG/raw/numpy/PDF are
        computed lazily from it on demand. When delegating to an ``mmdr``
        backend, this returns *mmdr's own* Diagram object directly — its
        API is identical by design, so no wrapping is needed.
    """
    if backend in (None, "js"):
        return Diagram(source, **opts)

    from .backends import backends

    try:
        import mmdr
    except ImportError as exc:
        raise ImportError(
            f"backend={backend!r} requires the optional 'mmdr' package. "
            "Install it with:\n    pip install mmdc[rust]"
        ) from exc

    if backend not in mmdr.backends():
        raise ValueError(f"Unknown backend {backend!r}. Available: {backends()!r}")
    return mmdr.render(source, backend=backend, **opts)
