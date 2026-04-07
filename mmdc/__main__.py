import argparse
import sys
import logging
from pathlib import Path
from . import MermaidConverter

def main():
    parser = argparse.ArgumentParser(
        description="Convert mermaid diagrams to SVG, PNG, or PDF using PhantomJS (phasma)"
    )
    parser.add_argument("-i", "--input", type=Path, required=True, help="Input mermaid file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output file (SVG, PNG, or PDF)")
    parser.add_argument("-w", "--width", type=int, help="Width of the generated diagram")
    parser.add_argument("-H", "--height", type=int, help="Height of the generated diagram")
    parser.add_argument("-s", "--scale", type=float, default=1.0, help="Scale factor for the output (default: 1.0)")
    parser.add_argument("-b", "--backgroundColor", dest="background", default="white", help="Background color (default: white)")
    parser.add_argument("-t", "--theme", default="default", choices=["default", "forest", "dark", "neutral"], help="Theme to use (default: default)")
    parser.add_argument("-c", "--configFile", type=Path, help="JSON configuration file for Mermaid")
    parser.add_argument("--cssFile", type=Path, help="CSS file to inject")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stderr)
        ]
    )

    converter = MermaidConverter(
        timeout=args.timeout
    )

    # Read the input file content
    input_content = args.input.read_text(encoding='utf-8')

    result = converter.convert(
        input=input_content,
        output_file=args.output,
        theme=args.theme,
        background=args.background,
        width=args.width,
        height=args.height,
        config_file=args.configFile,
        css_file=args.cssFile,
        scale=args.scale
    )
    # If output file is specified, result will be None on success
    # If output file is not specified, result will be the content on success
    success = (args.output is not None and result is None) or (args.output is None and result is not None)
    if success:
        logging.info(f"Successfully converted to {args.output}")
        sys.exit(0)
    else:
        logging.error("Conversion failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
