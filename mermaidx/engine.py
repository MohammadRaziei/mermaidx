"""
mermaidx.engine -- backward-compatible re-export.

The actual engine implementations now live in mermaidx.engines
(quickjs_engine.py / v8_engine.py), so that switching which JS engine
mermaidx.diagram uses is a single import-line change there instead of a
parameter. This module just re-exports the QuickJS one under the old
names, since it was the only one that used to exist here.
"""

from __future__ import annotations

from mermaidx.engines.quickjs_engine import Engine, MermaidRenderError
from mermaidx.path_bbox import _path_bbox  # kept for tests/test_samples.py

__all__ = ["Engine", "MermaidRenderError", "_path_bbox"]
