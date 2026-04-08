#!/usr/bin/env python3
"""
Mermaid Diagram Converter using PhantomJS (phasma) with runtime template replacement.
Supports SVG, PNG, PDF output.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Union, TextIO

from phasma.driver import Driver
# import cairosvg


class MermaidConverter:
    def __init__(self, timeout: int = 30):
        self.logger = logging.getLogger(__name__)
        # Determine assets directory relative to this file
        self.assets_dir = (Path(__file__).parent / "assets").resolve()
        self.render_js = "render.js"
        self.render_html = "render.html"
        self.timeout = timeout

        self.driver = Driver()
    
    def to_svg(self, input: Union[str, TextIO], output_file: Optional[Path] = None,
               css: Optional[str] = None, theme: Optional[str] = None,
               background: Optional[str] = None, width: Optional[int] = None,
               height: Optional[int] = None, config_file: Optional[Path] = None,
               css_file: Optional[Path] = None) -> Optional[str]:
        """
        Convert Mermaid diagram (text or file-like object) to SVG string or file.

        Args:
            input: Mermaid code as string, or a file-like object with .read() method
            output_file: Optional path to save SVG file. If None, returns string.
            css: Inline CSS to apply to the diagram
            theme: Theme to use for the diagram (default, forest, dark, neutral)
            background: Background color (default: white)
            width: Width of the diagram (default: 800)
            height: Height of the diagram (default: 600)
            config_file: Path to JSON config file for Mermaid
            css_file: Path to CSS file to apply to the diagram

        Returns:
            SVG content as string if output_file is None, otherwise None

        Raises:
            RuntimeError: If conversion fails
        """
        # Determine if input is a string or file-like object
        if isinstance(input, str):
            # String
            mermaid_code = input
        else:
            # File-like object
            mermaid_code = input.read()

        # Use default values or provided parameters
        theme = theme or "default"
        background = background or "white"
        # Use the explicitly provided width/height, otherwise None (will use natural size)
        config_file = config_file
        css_file = css_file

        # Build command arguments for render.js
        args = [str(self.render_js), "-", "svg"]

        # Add theme
        args.extend(["--theme", theme])

        # Add background
        args.extend(["--background", background])

        # Add dimensions only if explicitly provided (not None)
        if width is not None:
            args.extend(["--width", str(width)])
        if height is not None:
            args.extend(["--height", str(height)])

        # Add config file if provided
        if config_file is not None and config_file.exists():
            args.extend(["--configFile", str(config_file)])

        # Add CSS file if provided
        if css_file is not None and css_file.exists():
            args.extend(["--cssFile", str(css_file)])

        # Add inline CSS if provided
        if css is not None:
            args.extend(["--css", css])

        # Run phantomjs via phasma driver, read from stdin ("-") and output to stdout ("svg")
        result = self.driver.exec(
            args,
            capture_output=True,
            timeout=self.timeout,
            ssl=False,
            cwd=self.assets_dir,
            input=mermaid_code.encode()
        )

        stdout = result.stdout.decode() if result.stdout else ""
        stderr = result.stderr.decode() if result.stderr else ""

        self.logger.debug(f"stdout length: {len(stdout)} chars")
        self.logger.debug(f"stderr: {stderr}")

        # Check for errors in stderr (errors are written to stderr)
        if "ERROR:" in stderr or "ReferenceError" in stderr:
            raise RuntimeError(f"PhantomJS error: {stderr}")

        if result.returncode != 0:
            error = stderr if stderr else "Unknown error"
            raise RuntimeError(f"PhantomJS exited with code {result.returncode}: {error}")

        # If stdout is empty but no error, something went wrong
        if not stdout.strip():
            raise RuntimeError("No SVG content generated")

        # Success: stdout contains SVG
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(stdout)
            self.logger.debug(f"SVG written to {output_file}")
            return None
        else:
            return stdout
    
    def _render_to_file(self, input: Union[str, TextIO], output_file: Optional[Path],
                        file_extension: str, width: Optional[int] = None,
                        height: Optional[int] = None, resolution: int = 96,
                        background: Optional[str] = None, css: Optional[str] = None,
                        theme: Optional[str] = None, config_file: Optional[Path] = None,
                        css_file: Optional[Path] = None, scale: float = 1.0) -> Optional[bytes]:
        """
        Internal helper to render Mermaid to a file (PNG or PDF).

        Args:
            input: Mermaid code as string or file-like object
            output_file: Optional path to save file. If None, uses temp file.
            file_extension: '.png' or '.pdf'
            width: Output width in pixels
            height: Output height in pixels
            resolution: DPI resolution
            background: Background color
            css: Custom CSS
            theme: Theme to use for the diagram (default, forest, dark, neutral)
            config_file: Path to JSON config file for Mermaid
            css_file: Path to CSS file to apply to the diagram
            scale: Scale factor for output

        Returns:
            File bytes if output_file is None, otherwise None
        """
        import tempfile

        # Determine if input is a string or file-like object
        if isinstance(input, str):
            mermaid_code = input
        else:
            mermaid_code = input.read()

        # Use default values or provided parameters
        theme = theme or "default"
        background = background or "white"
        # Use the explicitly provided width/height, otherwise None (will use natural size)
        config_file = config_file
        css_file = css_file

        # If output_file is None, use a temporary file
        temp_file = None
        if output_file is None:
            temp_file = Path(tempfile.mktemp(suffix=file_extension))
            output_target = temp_file
        else:
            output_target = output_file

        # Build command arguments for render.js with named flags
        args = [str(self.render_js), "-", str(output_target)]

        # Add theme
        args.extend(["--theme", theme])

        # Add background
        args.extend(["--background", background])

        # Add dimensions only if explicitly provided (not None)
        if width is not None:
            args.extend(["--width", str(width)])
        if height is not None:
            args.extend(["--height", str(height)])

        # Add resolution if not default
        if resolution != 96:
            args.extend(["--resolution", str(resolution)])

        # Add scale if not default
        if scale != 1.0:
            args.extend(["--scale", str(scale)])

        # Add config file if specified
        if config_file is not None and config_file.exists():
            args.extend(["--configFile", str(config_file)])

        # Add CSS file if specified
        if css_file is not None and css_file.exists():
            args.extend(["--cssFile", str(css_file)])

        # Add CSS if specified
        if css is not None:
            args.extend(["--css", css])

        # Run phantomjs via phasma driver
        result = self.driver.exec(
            args,
            capture_output=True,
            timeout=self.timeout,
            ssl=False,
            cwd=self.assets_dir,
            input=mermaid_code.encode()
        )

        stdout = result.stdout if result.stdout else b""
        stderr = result.stderr.decode() if result.stderr else ""

        self.logger.debug(f"stdout length: {len(stdout)} bytes")
        self.logger.debug(f"stderr: {stderr}")

        # Check for errors
        if "ERROR:" in stderr or "ReferenceError" in stderr:
            raise RuntimeError(f"PhantomJS error: {stderr}")

        if result.returncode != 0:
            error = stderr if stderr else "Unknown error"
            raise RuntimeError(f"PhantomJS exited with code {result.returncode}: {error}")

        # If we used a temp file, read it and delete
        if temp_file:
            if temp_file.exists():
                file_bytes = temp_file.read_bytes()
                temp_file.unlink()
                return file_bytes
            else:
                raise RuntimeError(f"{file_extension.upper()} file was not created")
        else:
            # output_file was provided, no bytes to return
            return None
    
    def to_png(self, input: Union[str, TextIO], output_file: Optional[Path] = None,
               scale: float = 1.0, width: Optional[int] = None,
               height: Optional[int] = None, resolution: int = 96,
               background: Optional[str] = None, css: Optional[str] = None,
               theme: Optional[str] = None, config_file: Optional[Path] = None,
               css_file: Optional[Path] = None) -> Optional[bytes]:
        """
        Convert Mermaid diagram (text or file-like) to PNG bytes or file using PhantomJS.

        Args:
            input: Mermaid code as string, or a file-like object with .read() method
            output_file: Optional path to save PNG file. If None, returns bytes.
            scale: Scale factor for output (default 1.0) - overridden by width/height
            width: Output width in pixels (overrides scale)
            height: Output height in pixels (overrides scale)
            resolution: DPI resolution (default 96)
            background: Background color (default: white)
            css: Inline CSS to apply to the diagram
            theme: Theme to use for the diagram (default, forest, dark, neutral)
            config_file: Path to JSON config file for Mermaid
            css_file: Path to CSS file to apply to the diagram

        Returns:
            PNG bytes if output_file is None, otherwise None

        Raises:
            RuntimeError: If conversion fails
        """
        # Note: scale parameter is kept for backward compatibility but overridden by width/height
        return self._render_to_file(
            input=input,
            output_file=output_file,
            file_extension='.png',
            width=width,
            height=height,
            resolution=resolution,
            background=background,
            css=css,
            theme=theme,
            config_file=config_file,
            css_file=css_file,
            scale=scale
        )
    
    def to_pdf(self, input: Union[str, TextIO], output_file: Optional[Path] = None,
               scale: float = 1.0, width: Optional[int] = None,
               height: Optional[int] = None, resolution: int = 96,
               background: Optional[str] = None, css: Optional[str] = None,
               theme: Optional[str] = None, config_file: Optional[Path] = None,
               css_file: Optional[Path] = None) -> Optional[bytes]:
        """
        Convert Mermaid diagram (text or file-like) to PDF bytes or file using PhantomJS.

        Args:
            input: Mermaid code as string, or a file-like object with .read() method
            output_file: Optional path to save PDF file. If None, returns bytes.
            scale: Scale factor for output (default 1.0) - overridden by width/height
            width: Output width in pixels (overrides scale)
            height: Output height in pixels (overrides scale)
            resolution: DPI resolution (default 96)
            background: Background color (e.g., '#FFFFFF', 'transparent')
            css: Custom CSS to inject
            theme: Theme to use for the diagram (default, forest, dark, neutral)
            config_file: Path to JSON config file for Mermaid
            css_file: Path to CSS file to apply to the diagram

        Returns:
            PDF bytes if output_file is None, otherwise None

        Raises:
            RuntimeError: If conversion fails
        """
        # Note: scale parameter is kept for backward compatibility but overridden by width/height
        return self._render_to_file(
            input=input,
            output_file=output_file,
            file_extension='.pdf',
            width=width,
            height=height,
            resolution=resolution,
            background=background,
            css=css,
            theme=theme,
            config_file=config_file,
            css_file=css_file,
            scale=scale
        )
    
    def convert(self, input: Union[str, TextIO], output_file: Optional[Path] = None,
                theme: Optional[str] = None, background: Optional[str] = None,
                width: Optional[int] = None, height: Optional[int] = None,
                config_file: Optional[Path] = None, css_file: Optional[Path] = None,
                scale: float = 1.0) -> Optional[Union[str, bytes]]:
        """
        Convert Mermaid diagram to SVG, PNG, or PDF based on output file extension.
        If output_file is None, returns the content as string (for SVG) or bytes (for PNG/PDF).
        If output_file is provided, writes to the file and returns None.
        """
        try:
            # Determine if input is a string or Path object
            if isinstance(input, str):
                # String input
                mermaid_code = input
            elif isinstance(input, Path):
                # Path object - read the content
                mermaid_code = input.read_text(encoding="utf-8")
            else:
                # File-like object - read the content
                mermaid_code = input.read()

            # Convert output_file to absolute path if it's provided
            if output_file is not None:
                output_file = output_file.absolute()

            # Determine output format from the output_file extension
            if output_file is None:
                # If no output file is specified, default to SVG
                output_ext = ".svg"
            else:
                output_ext = output_file.suffix.lower()

            if output_ext == ".svg":
                result = self.to_svg(
                    input=mermaid_code,
                    output_file=output_file,
                    theme=theme,
                    background=background,
                    width=width,
                    height=height,
                    config_file=config_file,
                    css_file=css_file
                )
                if output_file is None:
                    self.logger.debug("SVG content generated")
                else:
                    self.logger.debug(f"SVG written to {output_file}")
                return result
            elif output_ext == ".png":
                result = self.to_png(
                    input=mermaid_code,
                    output_file=output_file,
                    theme=theme,
                    background=background,
                    width=width,
                    height=height,
                    config_file=config_file,
                    css_file=css_file,
                    scale=scale
                )
                if output_file is None:
                    self.logger.debug("PNG bytes generated")
                else:
                    self.logger.debug(f"PNG written to {output_file}")
                return result
            elif output_ext == ".pdf":
                result = self.to_pdf(
                    input=mermaid_code,
                    output_file=output_file,
                    theme=theme,
                    background=background,
                    width=width,
                    height=height,
                    config_file=config_file,
                    css_file=css_file,
                    scale=scale
                )
                if output_file is None:
                    self.logger.debug("PDF bytes generated")
                else:
                    self.logger.debug(f"PDF written to {output_file}")
                return result
            else:
                self.logger.error(f"Unsupported output format: {output_ext}. Use .svg, .png, or .pdf")
                return None

        except Exception as e:
            self.logger.error(f"Exception: {e}")
            return None
