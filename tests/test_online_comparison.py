"""
Structural comparison against mermaid.ink (a hosted mermaid-cli/puppeteer
service) — NOT pixel-diffing, since mermaid.ink renders with real Chrome and
whatever mermaid version it currently runs, while mmdc renders with QuickJS
+ resvg and a bundled font. Two different engines will never be pixel-
identical. What should agree:

  - the same text labels appear
  - the same rough number of shapes/edges appear
  - the aspect ratio is in the same ballpark (same layout algorithm family)

These tests need internet access to https://mermaid.ink and are skipped
(not failed) if it's unreachable, so they don't break offline/CI runs where
outbound network access isn't available.

Only the standard library is used for the HTTP calls (`urllib.request`) —
there's no need for `httpx` or `requests` for a couple of simple GETs.
"""

from __future__ import annotations

import base64
import re
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import pytest

from mmdc import MermaidConverter
from mmdc.png_decode import decode_png

MERMAID_INK_TIMEOUT = 10  # seconds

DIAGRAMS = {
    "flowchart": "graph TD\n    A[Start] --> B{Is it working?}\n    B -->|Yes| C[Great]\n    B -->|No| D[Debug]",
    "sequence": "sequenceDiagram\n    Alice->>Bob: Hello\n    Bob-->>Alice: Hi there",
}


def _mermaid_ink_b64(code: str) -> str:
    return base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mmdc-test-suite"})
    with urllib.request.urlopen(req, timeout=MERMAID_INK_TIMEOUT) as resp:
        return resp.read()


@pytest.fixture(scope="module")
def _require_mermaid_ink():
    """Skip the whole module if mermaid.ink isn't reachable from here."""
    try:
        _fetch("https://mermaid.ink/svg/" + _mermaid_ink_b64("graph LR\nA-->B"))
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        pytest.skip(f"mermaid.ink not reachable: {e}")


def _svg_texts(svg_bytes_or_str) -> list[str]:
    svg_str = svg_bytes_or_str.decode("utf-8") if isinstance(svg_bytes_or_str, bytes) else svg_bytes_or_str
    root = ET.fromstring(svg_str)
    return sorted(
        el.text.strip()
        for el in root.iter()
        if el.tag.split("}")[-1] in ("text", "tspan") and el.text and el.text.strip()
    )


def _svg_aspect_ratio(svg_bytes_or_str) -> float:
    svg_str = svg_bytes_or_str.decode("utf-8") if isinstance(svg_bytes_or_str, bytes) else svg_bytes_or_str
    m = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_str)
    assert m, "no viewBox found"
    _, _, w, h = (float(x) for x in m.group(1).split())
    return w / h


@pytest.mark.parametrize("name", DIAGRAMS)
@pytest.mark.usefixtures("_require_mermaid_ink")
def test_svg_labels_match_mermaid_ink(name):
    code = DIAGRAMS[name]
    reference_svg = _fetch("https://mermaid.ink/svg/" + _mermaid_ink_b64(code))
    reference_texts = _svg_texts(reference_svg)

    import asyncio

    async def _render():
        async with MermaidConverter() as m:
            return await m.to_svg(code)

    ours_svg = asyncio.run(_render())
    our_texts = _svg_texts(ours_svg)

    # Compare as multisets of *words* rather than exact tspan groupings:
    # mermaid.ink's Chrome and our engine may wrap long labels into a
    # different number of <tspan> line-break fragments for the same text.
    reference_words = sorted(" ".join(reference_texts).split())
    our_words = sorted(" ".join(our_texts).split())
    assert our_words == reference_words, (
        f"label text mismatch for {name!r}:\n"
        f"  mermaid.ink: {reference_words}\n"
        f"  ours:        {our_words}"
    )


@pytest.mark.parametrize("name", DIAGRAMS)
@pytest.mark.usefixtures("_require_mermaid_ink")
def test_svg_aspect_ratio_close_to_mermaid_ink(name):
    code = DIAGRAMS[name]
    reference_svg = _fetch("https://mermaid.ink/svg/" + _mermaid_ink_b64(code))
    reference_ratio = _svg_aspect_ratio(reference_svg)

    import asyncio

    async def _render():
        async with MermaidConverter() as m:
            return await m.to_svg(code)

    ours_svg = asyncio.run(_render())
    our_ratio = _svg_aspect_ratio(ours_svg)

    # generous tolerance: different engines wrap/size labels slightly
    # differently, which shifts node dimensions and thus overall aspect ratio
    rel_diff = abs(our_ratio - reference_ratio) / reference_ratio
    assert rel_diff < 0.35, (
        f"aspect ratio for {name!r} differs too much: "
        f"ours={our_ratio:.3f} mermaid.ink={reference_ratio:.3f} (Δ={rel_diff:.0%})"
    )


@pytest.mark.parametrize("name", DIAGRAMS)
@pytest.mark.usefixtures("_require_mermaid_ink")
def test_png_dimensions_close_to_mermaid_ink(name):
    code = DIAGRAMS[name]
    reference_png = _fetch(
        "https://mermaid.ink/img/" + _mermaid_ink_b64(code) + "?type=png"
    )
    ref = decode_png(reference_png)
    reference_ratio = ref.width / ref.height

    import asyncio

    async def _render():
        async with MermaidConverter() as m:
            return await m.to_png(code)

    ours_png = asyncio.run(_render())
    ours = decode_png(ours_png)
    our_ratio = ours.width / ours.height

    rel_diff = abs(our_ratio - reference_ratio) / reference_ratio
    assert rel_diff < 0.35, (
        f"PNG aspect ratio for {name!r} differs too much: "
        f"ours={our_ratio:.3f} ({ours.width}x{ours.height}) "
        f"mermaid.ink={reference_ratio:.3f} ({ref.width}x{ref.height})"
    )
