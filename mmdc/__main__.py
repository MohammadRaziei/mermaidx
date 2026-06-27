"""
mmdc CLI — python -m mmdc

Convert Mermaid diagrams to SVG, PNG, or PDF.

Examples:
    mmdc -i diagram.mermaid                    # SVG to stdout
    mmdc -i diagram.mermaid -o diagram.svg
    mmdc -i diagram.mermaid -o diagram.png --scale 2.0
    mmdc -i diagram.mermaid -o diagram.pdf --pdf-format A4
    cat diagram.mermaid | mmdc -i -
    mmdc --info
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mmdc import MermaidConverter


def _get_version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("mmdc")
    except Exception:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmdc",
        description="Convert Mermaid diagrams to SVG, PNG, or PDF — fully offline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  mmdc -i diagram.mermaid                         # SVG to stdout
  mmdc -i diagram.mermaid -o diagram.svg
  mmdc -i diagram.mermaid -o diagram.png --scale 2.0
  mmdc -i diagram.mermaid -o diagram.pdf
  mmdc -i diagram.mermaid -o diagram.pdf --pdf-format A4 --landscape
  mmdc -i diagram.mermaid -o diagram.svg --theme dark --background "#f5f5f5"
  cat diagram.mermaid | mmdc -i -
  mmdc --info
        """,
    )

    parser.add_argument("--version", "-V", action="version", version=_get_version())
    parser.add_argument("--info", action="store_true",
                        help="Print Mermaid library version and exit")
    parser.add_argument("-i", "--input", metavar="FILE",
                        help="Input Mermaid file, or '-' to read from stdin")
    parser.add_argument("-o", "--output", default=None, metavar="FILE",
                        help="Output file (.svg/.png/.pdf). Omit to write SVG to stdout.")
    parser.add_argument("-s", "--scale", type=float, default=1.0, metavar="N",
                        help="Scale factor for PNG/PDF (default: 1.0)")
    parser.add_argument("-t", "--theme",
                        choices=["default", "forest", "dark", "neutral"],
                        default="default",
                        help="Mermaid theme (default: default)")
    parser.add_argument("-b", "--background", default="white", metavar="COLOR",
                        help="CSS background color (default: white)")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="JSON config file for Mermaid")
    parser.add_argument("--css", metavar="FILE",
                        help="CSS file to inject into the diagram")
    parser.add_argument("--pdf-format", default=None, metavar="FORMAT",
                        help="PDF paper format e.g. A4, Letter (default: fit to diagram)")
    parser.add_argument("--landscape", action="store_true",
                        help="Landscape orientation (PDF only)")
    parser.add_argument("--margin", default="0", metavar="MARGIN",
                        help="PDF margin e.g. '1cm' (default: 0)")

    return parser



async def _run(args) -> None:
    if args.input == "-":
        source = sys.stdin.read()
    else:
        source = args.input

    config = None
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    css = None
    if args.css:
        css = Path(args.css).read_text(encoding="utf-8")

    async with MermaidConverter(theme=args.theme, background=args.background) as m:
        if args.output is None:
            # no -o → render SVG and write to stdout
            data = await m.to_svg(source, config=config, css=css)
            sys.stdout.buffer.write(data)
        else:
            output = Path(args.output)
            data = await m.convert(
                source, output,
                scale=args.scale,
                config=config,
                css=css,
                pdf_format=args.pdf_format,
                pdf_landscape=args.landscape,
                pdf_margin=args.margin,
            )
            print(f"saved to {output}  ({len(data):,} bytes)", file=sys.stderr)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.info:
        import xml.etree.ElementTree as ET

        async def _info():
            async with MermaidConverter() as m:
                svg = await m.to_svg("info")
            svg_str = svg.decode("utf-8") if isinstance(svg, bytes) else svg
            root = ET.fromstring(svg_str)
            # only <text> elements, skip <style> and <script>
            ns = {"svg": "http://www.w3.org/2000/svg"}
            texts = []
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == "text" and el.text and el.text.strip():
                    texts.append(el.text.strip())
            print(" ".join(texts))

        asyncio.run(_info())
        return

    if not args.input:
        parser.error("the following arguments are required: -i/--input")

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
    