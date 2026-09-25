"""
mermaidx.pdf_writer — hand-written, dependency-free PDF generation.

Every mainstream "put a raster image on a PDF page" library (Pillow,
pikepdf, img2pdf, reportlab) pulls in Pillow as a transitive dependency.
Since mermaidx.raster already gives us decoded, real pixels (via mermaidx.png_decode),
building the PDF objects directly is a bounded, well-specified task and
avoids that dependency entirely — this only uses `zlib` and `struct` from
the standard library.

The PDF written here is intentionally minimal: one page, one image XObject
(plus an /SMask object if the image has transparency), a content stream
that places it with a `cm`+`Do`, and a classic (non-cross-reference-stream)
xref table. That's all a single-diagram PDF needs.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

from mermaidx.png_decode import DecodedPNG

_MM_PER_INCH = 25.4
_PDF_PT_PER_PX = 72 / 96  # PDF points are 1/72in; we treat px as 1/96in (CSS px)

_PAPER_SIZES_MM = {
    "a3": (297, 420), "a4": (210, 297), "a5": (148, 210),
    "letter": (216, 279), "legal": (216, 356), "tabloid": (279, 432),
}


def _mm_to_pt(mm: float) -> float:
    return mm / _MM_PER_INCH * 72


def paper_size_pt(fmt: str, landscape: bool) -> tuple[float, float]:
    key = fmt.strip().lower()
    if key not in _PAPER_SIZES_MM:
        raise ValueError(f"Unknown pdf_format {fmt!r}. Known: {sorted(_PAPER_SIZES_MM)}")
    w_mm, h_mm = _PAPER_SIZES_MM[key]
    w, h = _mm_to_pt(w_mm), _mm_to_pt(h_mm)
    return (h, w) if landscape else (w, h)


def parse_length_pt(value) -> float:
    """Parse a CSS-style length ('1cm', '10mm', '0.5in', '20px', '0', 12) to PDF points."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) * _PDF_PT_PER_PX
    s = str(value).strip().lower()
    m = re.match(r"^(-?\d+\.?\d*)\s*(px|cm|mm|in|pt)?$", s)
    if not m:
        raise ValueError(f"Unrecognized length: {value!r}")
    num, unit = float(m.group(1)), (m.group(2) or "px")
    return {
        "px": num * _PDF_PT_PER_PX,
        "cm": _mm_to_pt(num * 10),
        "mm": _mm_to_pt(num),
        "in": num * 72,
        "pt": num,
    }[unit]


@dataclass
class _Obj:
    num: int
    body: bytes  # everything between "N 0 obj" and "endobj" (exclusive)


class _PDFBuilder:
    def __init__(self) -> None:
        self._objects: list[bytes] = []  # index 0 unused; PDF objects are 1-indexed

    def add(self, body: bytes) -> int:
        self._objects.append(body)
        return len(self._objects)  # this object's number

    def build(self, root_obj_num: int) -> bytes:
        out = BytesIO()
        out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, body in enumerate(self._objects, start=1):
            offsets.append(out.tell())
            out.write(f"{i} 0 obj\n".encode("ascii"))
            out.write(body)
            out.write(b"\nendobj\n")
        xref_offset = out.tell()
        n = len(self._objects) + 1
        out.write(f"xref\n0 {n}\n".encode("ascii"))
        out.write(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.write(f"{off:010d} 00000 n \n".encode("ascii"))
        out.write(
            f"trailer\n<< /Size {n} /Root {root_obj_num} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF".encode("ascii")
        )
        return out.getvalue()


def png_to_pdf(
    png: DecodedPNG,
    *,
    pdf_format: Optional[str] = None,
    landscape: bool = False,
    margin: str = "0",
    scale: float = 1.0,
    background_color: Optional[str] = None,
) -> bytes:
    """
    Build a single-page PDF embedding `png`'s pixels.

    If pdf_format is None: the page is sized to fit the (scaled) image
    exactly (no visible margin). Otherwise the image is centered on the
    given paper format, inset by `margin`.
    """
    b = _PDFBuilder()

    img_w_pt = png.width * _PDF_PT_PER_PX * scale
    img_h_pt = png.height * _PDF_PT_PER_PX * scale

    if pdf_format is None:
        page_w, page_h = img_w_pt, img_h_pt
        tx, ty, draw_w, draw_h = 0.0, 0.0, img_w_pt, img_h_pt
    else:
        page_w, page_h = paper_size_pt(pdf_format, landscape)
        margin_pt = parse_length_pt(margin)
        content_w = max(page_w - 2 * margin_pt, 1.0)
        content_h = max(page_h - 2 * margin_pt, 1.0)
        # uniform "meet" scaling within the content box, centered
        fit_scale = min(content_w / img_w_pt, content_h / img_h_pt)
        draw_w, draw_h = img_w_pt * fit_scale, img_h_pt * fit_scale
        tx = margin_pt + (content_w - draw_w) / 2
        ty = page_h - margin_pt - (content_h - draw_h) / 2 - draw_h

    # -- optional SMask (alpha channel) --
    smask_num = None
    if png.has_alpha:
        alpha_stream = zlib.compress(png.alpha, 9)
        smask_body = (
            f"<< /Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
            f"/Length {len(alpha_stream)} >>\nstream\n"
        ).encode("ascii") + alpha_stream + b"\nendstream"
        smask_num = b.add(smask_body)

    # -- image XObject --
    rgb_stream = zlib.compress(png.rgb, 9)
    smask_ref = f" /SMask {smask_num} 0 R" if smask_num else ""
    image_body = (
        f"<< /Type /XObject /Subtype /Image /Width {png.width} /Height {png.height} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
        f"/Length {len(rgb_stream)}{smask_ref} >>\nstream\n"
    ).encode("ascii") + rgb_stream + b"\nendstream"
    image_num = b.add(image_body)

    # -- content stream: optional background fill, then place the image --
    ops = []
    if background_color and png.has_alpha:
        r, g, gg = _color_to_rgb01(background_color)
        ops.append(f"{r:.4f} {g:.4f} {gg:.4f} rg 0 0 {page_w:.2f} {page_h:.2f} re f")
    ops.append(f"q {draw_w:.4f} 0 0 {draw_h:.4f} {tx:.4f} {ty:.4f} cm /Im0 Do Q")
    content = "\n".join(ops).encode("ascii")
    content_stream = zlib.compress(content, 9)
    content_body = (
        f"<< /Length {len(content_stream)} /Filter /FlateDecode >>\nstream\n"
    ).encode("ascii") + content_stream + b"\nendstream"
    content_num = b.add(content_body)

    # -- page / pages / catalog --
    resources = f"<< /XObject << /Im0 {image_num} 0 R >> >>"
    page_body = (
        f"<< /Type /Page /Parent {{PAGES}} 0 R "
        f"/MediaBox [0 0 {page_w:.4f} {page_h:.4f}] "
        f"/Resources {resources} /Contents {content_num} 0 R >>"
    )
    # Pages object needs the page's number, and the page needs the pages
    # object's number -- reserve the page number first, patch parent after.
    page_num = b.add(page_body.replace("{PAGES}", "0").encode("ascii"))
    pages_body = f"<< /Type /Pages /Kids [{page_num} 0 R] /Count 1 >>"
    pages_num = b.add(pages_body.encode("ascii"))
    b._objects[page_num - 1] = page_body.replace("{PAGES}", str(pages_num)).encode("ascii")
    catalog_body = f"<< /Type /Catalog /Pages {pages_num} 0 R >>"
    catalog_num = b.add(catalog_body.encode("ascii"))

    return b.build(catalog_num)


def _color_to_rgb01(color: str) -> tuple[float, float, float]:
    """Parse a very small subset of CSS colors (#rgb, #rrggbb, named) to 0..1 floats."""
    c = color.strip().lower()
    named = {
        "white": "#ffffff", "black": "#000000", "transparent": "#ffffff",
        "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
        "gray": "#808080", "grey": "#808080",
    }
    c = named.get(c, c)
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r, g, bl = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return r / 255, g / 255, bl / 255
    return 1.0, 1.0, 1.0  # unknown -> white
