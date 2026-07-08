"""
mmdc.png_decode — just enough of the PNG spec to pull raw RGB(A) pixels back
out of a PNG file, using only the standard library (`zlib`, `struct`).

Why this exists: resvg only emits PNG bytes. To embed those pixels into a
hand-written PDF (see mmdc.pdf_writer) as an image XObject, or to hand back
raw RGBA8888 buffers (Diagram.raw() / .numpy()), we need actual samples, not
a PNG container — and every mainstream "give me a raster image" library
(Pillow, pikepdf, img2pdf, reportlab...) pulls in Pillow as a transitive
dependency. This avoids that entirely.

Supports exactly what resvg produces: 8-bit, non-interlaced, color type 2
(RGB) or 6 (RGBA). That covers all resvg output; nothing else is handled.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass


@dataclass
class DecodedPNG:
    width: int
    height: int
    has_alpha: bool
    rgb: bytes    # interleaved R,G,B bytes, width*height*3
    alpha: bytes  # one byte per pixel, width*height (empty if has_alpha is False)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data: bytes) -> DecodedPNG:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")

    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    n = len(data)
    while pos < n:
        length = struct.unpack_from(">I", data, pos)[0]
        ctype = data[pos + 4:pos + 8]
        body_start = pos + 8
        body = data[body_start:body_start + length]
        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", body[:10])
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos = body_start + length + 4  # skip CRC

    if width is None:
        raise ValueError("Missing IHDR")
    if bit_depth != 8 or color_type not in (2, 6):
        raise ValueError(
            f"Unsupported PNG: bit_depth={bit_depth} color_type={color_type} "
            "(only 8-bit RGB/RGBA, as produced by resvg, is supported)"
        )

    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(bytes(idat))

    stride = width * channels
    out = bytearray(stride * height)
    prev_row = bytearray(stride)
    src_pos = 0
    for y in range(height):
        filter_type = raw[src_pos]
        src_pos += 1
        row = bytearray(raw[src_pos:src_pos + stride])
        src_pos += stride

        if filter_type == 0:
            pass
        elif filter_type == 1:  # Sub
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                row[i] = (row[i] + prev_row[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((left + prev_row[i]) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = prev_row[i]
                up_left = prev_row[i - channels] if i >= channels else 0
                row[i] = (row[i] + _paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"Unsupported PNG filter type: {filter_type}")

        out[y * stride:(y + 1) * stride] = row
        prev_row = row

    if channels == 3:
        return DecodedPNG(width, height, False, bytes(out), b"")

    rgb = bytearray(width * height * 3)
    alpha = bytearray(width * height)
    for p in range(width * height):
        rgb[p * 3:p * 3 + 3] = out[p * 4:p * 4 + 3]
        alpha[p] = out[p * 4 + 3]
    return DecodedPNG(width, height, True, bytes(rgb), bytes(alpha))


def decode_png_rgba(data: bytes) -> tuple[bytes, int, int]:
    """Like decode_png(), but returns interleaved RGBA8888 bytes directly —
    convenient for APIs that want a single (bytes, width, height) tuple
    (e.g. Diagram.raw() / .numpy())."""
    d = decode_png(data)
    rgba = bytearray(d.width * d.height * 4)
    if d.has_alpha:
        for p in range(d.width * d.height):
            rgba[p * 4:p * 4 + 3] = d.rgb[p * 3:p * 3 + 3]
            rgba[p * 4 + 3] = d.alpha[p]
    else:
        for p in range(d.width * d.height):
            rgba[p * 4:p * 4 + 3] = d.rgb[p * 3:p * 3 + 3]
            rgba[p * 4 + 3] = 255
    return bytes(rgba), d.width, d.height
