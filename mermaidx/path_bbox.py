"""
mermaidx.path_bbox — `getBBox()` of an SVG <path>.

There is exactly one implementation: assets/path_bbox.js (Blink's path building + Skia's tight bounds, in
float32 like Chrome). Both JS engines evaluate it directly (`PATH_BBOX_JS`), so a bbox never crosses the
Python/JS boundary while rendering. `path_bbox()` below runs that same source in a QuickJS context of its own,
for Python callers (tests); it is not a second implementation.
"""

from __future__ import annotations

import functools
import json
import pathlib

_SOURCE = pathlib.Path(__file__).parent / "assets" / "path_bbox.js"
PATH_BBOX_JS = _SOURCE.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _context():
    import quickjs

    ctx = quickjs.Context()
    ctx.eval(PATH_BBOX_JS)
    return ctx


def path_bbox(d: str) -> dict:
    """{"x", "y", "width", "height"} of the path `d`, as Chrome's getBBox() returns it."""
    return json.loads(_context().eval(f"JSON.stringify(__pathBBox({json.dumps(d)}))"))


# Name the other modules import (kept so existing imports keep working).
_path_bbox = path_bbox
