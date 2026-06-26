"""
mmdc CLI — python -m mmdc

Convert Mermaid diagrams to SVG, PNG, or PDF.

Examples:
    mmdc -i diagram.mermaid -o diagram.svg
    mmdc -i diagram.mermaid -o diagram.png --scale 2.0
    mmdc -i diagram.mermaid -o diagram.pdf --theme dark
    mmdc -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape
    cat diagram.mermaid | mmdc -i - -o diagram.svg
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mmdc import MermaidConverter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmdc",
        description="Convert Mermaid diagrams to SVG, PNG, or PDF — fully offline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  mmdc -i diagram.mermaid -o diagram.svg
  mmdc -i diagram.mermaid -o diagram.png --scale 2.0
  mmdc -i diagram.mermaid -o diagram.pdf
  mmdc -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape
  mmdc -i diagram.mermaid -o diagram.svg --theme dark --background "#f5f5f5"
  cat diagram.mermaid | mmdc -i - -o diagram.svg
        """,
    )

    parser.add_argument(
        "--version", "-V",
        action="version",
        version=_get_version(),
    )
    parser.add_argument(
        "-i", "--input", required=True, metavar="FILE",
        help="Input Mermaid file, or '-' to read from stdin",
    )
    parser.add_argument(
        "-o", "--output", required=True, metavar="FILE",
        help="Output file — format inferred from extension (.svg, .png, .pdf)",
    )
    parser.add_argument(
        "-s", "--scale", type=float, default=1.0, metavar="N",
        help="Scale factor for PNG/PDF output (default: 1.0)",
    )
    parser.add_argument(
        "-t", "--theme",
        choices=["default", "forest", "dark", "neutral"],
        default="default",
        help="Mermaid theme (default: default)",
    )
    parser.add_argument(
        "-b", "--background", default="white", metavar="COLOR",
        help="CSS background color (default: white)",
    )
    parser.add_argument(
        "-c", "--config", metavar="FILE",
        help="JSON config file for Mermaid",
    )
    parser.add_argument(
        "--css", metavar="FILE",
        help="CSS file to inject into the diagram",
    )
    parser.add_argument(
        "--pdf-format", default=None, metavar="FORMAT",
        help="PDF paper format e.g. A4, Letter. Omit to fit paper to diagram size.",
    )
    parser.add_argument(
        "--landscape", action="store_true",
        help="Landscape orientation (PDF only)",
    )
    parser.add_argument(
        "--margin", default="0", metavar="MARGIN",
        help="PDF margin e.g. '1cm', '10px' (default: 0)",
    )

    return parser


def _get_version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("mmdc")
    except Exception:
        return "unknown"


async def _run(args) -> None:
    # read input
    if args.input == "-":
        source = sys.stdin.read()
    else:
        source = args.input  # MermaidConverter handles file vs string

    # read optional config
    config = None
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    # read optional CSS
    css = None
    if args.css:
        css = Path(args.css).read_text(encoding="utf-8")

    output = Path(args.output)

    async with MermaidConverter(theme=args.theme, background=args.background) as m:
        data = await m.convert(
            source,
            output,
            scale=args.scale,
            config=config,
            css=css,
            pdf_format=args.pdf_format,
            pdf_landscape=args.landscape,
            pdf_margin=args.margin,
        )

    print(f"saved to {output}  ({len(data):,} bytes)")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
    