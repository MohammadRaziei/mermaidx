"""
mermaidx CLI — python -m mermaidx

Convert Mermaid diagrams to SVG, PNG, or PDF. Fully synchronous: rendering
is CPU-bound (no browser process, no I/O to wait on), so there's no event
loop here at all -- one less thing to start up.

Examples:
    mermaidx -i diagram.mermaid                    # SVG to stdout
    mermaidx -i diagram.mermaid -f png -o -        # PNG to stdout
    mermaidx -i diagram.mermaid -f png --data-uri  # data:image/png;base64,... to stdout
    mermaidx -i diagram.mermaid -o diagram.svg
    mermaidx -i diagram.mermaid -o diagram.png -w 1200
    mermaidx -i diagram.mermaid -o diagram.pdf --pdf-format A4
    cat diagram.mermaid | mermaidx -i -
    mermaidx --info
    mermaidx --list-backends
    mermaidx -i diagram.mermaid --backend rust:merman -o diagram.svg
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import mermaidx
from mermaidx.diagram import Diagram

_FORMATS = ("svg", "png", "jpg", "jpeg", "bmp", "tga", "pdf")
_MIME = {
    "svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "bmp": "image/bmp",
    "tga": "image/x-tga", "pdf": "application/pdf",
}


def _get_version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("mermaidx")
    except Exception:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mermaidx",
        description="Convert Mermaid diagrams to SVG, PNG, or PDF — fully offline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  mermaidx -i diagram.mermaid                         # SVG to stdout
  mermaidx -i diagram.mermaid -f png -o - | display   # PNG to stdout
  mermaidx -i diagram.mermaid -f png --data-uri       # data:image/png;base64,... to stdout
  mermaidx -i diagram.mermaid -o diagram.svg
  mermaidx -i diagram.mermaid -o diagram.png -w 1200
  mermaidx -i diagram.mermaid -o diagram.png --scale 2.0
  mermaidx -i diagram.mermaid -o diagram.pdf
  mermaidx -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape
  mermaidx -i diagram.mermaid -o diagram.svg --theme dark
  cat diagram.mermaid | mermaidx -i -
  mermaidx --info
  mermaidx --list-backends
  mermaidx -i diagram.mermaid --backend rust:merman -o diagram.svg
        """,
    )

    parser.add_argument("--version", "-v", action="version", version=_get_version())
    parser.add_argument("--info", action="store_true",
                        help="Print Mermaid library version and exit")
    parser.add_argument("--list-backends", action="store_true",
                        help="List available rendering backends and exit")
    parser.add_argument("--backend", default=None, metavar="KIND:NAME",
                        help="Rendering backend to use, e.g. js:mermaid, js:pele or rust:merman "
                             "(default: js:mermaid). See --list-backends for what's available.")
    parser.add_argument("--engine", default=None, metavar="NAME",
                        help="JS engine for a js: backend: quickjs or v8 (default: quickjs). "
                             "Not valid with a rust: backend.")
    parser.add_argument("-i", "--input", metavar="FILE",
                        help="Input Mermaid file, or '-' to read from stdin")
    parser.add_argument("-o", "--output", default=None, metavar="FILE",
                        help="Output file (.svg/.png/.jpg/.jpeg/.bmp/.tga/.pdf), or '-' for stdout. "
                             "Omit to write to stdout too.")
    parser.add_argument("-f", "--format", default=None, choices=_FORMATS, metavar="FORMAT",
                        help="Output format: " + ", ".join(_FORMATS) + ". Overrides the extension of -o, "
                             "and is the only way to pick one for stdout (default: the extension of -o, "
                             "or svg for stdout).")
    parser.add_argument("--data-uri", action="store_true",
                        help="Write the output to stdout as a data URI (data:image/png;base64,...) instead of "
                             "raw bytes, for embedding in HTML/Markdown/JSON or for a terminal. "
                             "Stdout only (no -o FILE).")
    parser.add_argument("-w", "--width", type=float, default=None, metavar="N",
                        help="Output width in pixels (PNG/PDF-fit)")
    parser.add_argument("-H", "--height", type=float, default=None, metavar="N",
                        help="Output height in pixels (PNG/PDF-fit)")
    parser.add_argument("--scale", type=float, default=None, metavar="N",
                        help="Size multiplier, used if -w/-H are omitted (e.g. 2.0)")
    parser.add_argument("-t", "--theme",
                        choices=["default", "base", "dark", "forest", "neutral", "neo", "neo-dark", "redux",
                                 "redux-dark", "redux-color", "redux-dark-color", "null"],
                        default=None,
                        help="Mermaid theme (default: the one Mermaid picks for each diagram type, like mmdc)")
    parser.add_argument("-b", "--background", default=None, metavar="COLOR",
                        help="CSS background color (default: transparent)")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="JSON config file for Mermaid (js: backends only)")
    parser.add_argument("--css", metavar="FILE",
                        help="CSS file to inject into the diagram (js: backends only)")
    parser.add_argument("--quality", type=int, default=None, metavar="N",
                        help="JPEG quality 1-100 (default: 90). JPEG output only. "
                             "JPEG has no transparency: -b/--background defaults to white for it.")
    parser.add_argument("--pdf-format", default=None, metavar="FORMAT",
                        help="PDF paper format e.g. A4, Letter (default: fit to diagram)")
    parser.add_argument("--landscape", action="store_true",
                        help="Landscape orientation (PDF only)")
    parser.add_argument("--margin", default="0", metavar="MARGIN",
                        help="PDF margin e.g. '1cm' (default: 0)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress informational messages (e.g. 'saved to ... bytes')")

    return parser


def _read_source(input_arg: str) -> str:
    if input_arg == "-":
        return sys.stdin.read()
    return Path(input_arg).read_text(encoding="utf-8")


def _print_info() -> None:
    import xml.etree.ElementTree as ET

    svg_str = Diagram("info").svg()
    root = ET.fromstring(svg_str)
    texts = [
        el.text.strip()
        for el in root.iter()
        if el.tag.split("}")[-1] == "text" and el.text and el.text.strip()
    ]
    print(" ".join(texts))


def _print_backends() -> None:
    for name in mermaidx.backends():
        marker = " (default)" if name == "js:mermaid" else ""
        print(f"{name}{marker}")
    print("engines (for js: backends):")
    for name in mermaidx.available_engines():
        marker = " (default)" if name == "quickjs" else ""
        print(f"  {name}{marker}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.info:
        _print_info()
        return

    if args.list_backends:
        _print_backends()
        return

    if not args.input:
        parser.error("the following arguments are required: -i/--input")

    source = _read_source(args.input)
    config = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else None
    css = Path(args.css).read_text(encoding="utf-8") if args.css else None

    backend = args.backend or "js:mermaid"
    render_kwargs = {"theme": args.theme}
    if backend.startswith("js:"):
        render_kwargs.update(config=config, css=css)
    elif config or css:
        print(f"warning: --config/--css are ignored for backend={backend!r} "
              "(only the js: backends support them)", file=sys.stderr)

    try:
        d = mermaidx.render(source, backend=args.backend, engine=args.engine, **render_kwargs)
    except ValueError as exc:  # a bad --backend / --engine / --theme combination: say so, no traceback
        parser.error(str(exc))

    to_stdout = args.output is None or args.output == "-"
    output = None if to_stdout else Path(args.output)

    fmt = args.format
    if fmt is None:
        fmt = "svg" if to_stdout else Diagram._EXTENSION_FORMATS.get(output.suffix.lower())
        if fmt is None:
            parser.error(f"cannot infer the output format from {args.output!r}: use one of the extensions "
                         f"{sorted(Diagram._EXTENSION_FORMATS)} or pass -f/--format")
    if fmt == "jpeg":
        fmt = "jpg"

    if args.data_uri and not to_stdout:
        parser.error("--data-uri writes to standard output: drop -o FILE (or use -o -)")
    if to_stdout and fmt != "svg" and not args.data_uri and sys.stdout.isatty():
        parser.error(f"refusing to write binary {fmt} to a terminal: redirect it (> out.{fmt}) "
                     "or pass --data-uri to get it as text")

    raster_kwargs = {"width": args.width, "height": args.height, "scale": args.scale, "background": args.background}
    format_opts = {}
    if fmt == "pdf":
        format_opts = {"pdf_format": args.pdf_format, "pdf_landscape": args.landscape, "pdf_margin": args.margin}
    elif fmt == "jpg" and args.quality is not None:
        format_opts = {"quality": args.quality}

    if to_stdout:
        data = _encode(d, fmt, raster_kwargs, format_opts)
        if args.data_uri:
            data = f"data:{_MIME[fmt]};base64,{base64.b64encode(data).decode('ascii')}\n".encode("ascii")
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return

    d.save(str(output), format=fmt, **(raster_kwargs if fmt != "svg" else {}), **format_opts)

    if not args.quiet:
        print(f"saved to {output}  ({output.stat().st_size:,} bytes)", file=sys.stderr)


def _encode(d: Diagram, fmt: str, raster_kwargs: dict, format_opts: dict) -> bytes:
    """The bytes of *d* in *fmt* (what ``Diagram.save`` would write), for standard output."""
    if fmt == "svg":
        return d.svg().encode("utf-8")
    if fmt == "pdf":
        return d.pdf(**{**raster_kwargs, "scale": raster_kwargs["scale"] or 1.0}, **format_opts)
    return getattr(d, fmt)(**raster_kwargs, **format_opts)


if __name__ == "__main__":
    main()
