"""Tests for mermaidx.engines.v8_engine's subprocess-based memory safety.

mindmap diagrams schedule an internal animation loop that never stops on
its own (see v8_engine.py's module docstring) -- py_mini_racer has no way
to interrupt it in-process, so the V8 isolate that gets stuck running it
lives in a child *process* instead of a thread: on timeout, that process is
killed outright (SIGKILL) and the OS reclaims 100% of its memory
immediately, unconditionally. These tests use a short render_timeout_ms to
exercise that path quickly rather than waiting out the real 8s default.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time

import psutil
import pytest

pytest.importorskip("py_mini_racer")

from mermaidx.engines.v8_engine import Engine, MermaidRenderError  # noqa: E402

MINDMAP = "mindmap\n  root((mindmap))\n    Origins\n      Long history\n"
FLOWCHART = "flowchart TD\nA-->B"


@pytest.fixture
def engine():
    eng = Engine(render_timeout_ms=3000)  # short, just to exercise the path quickly
    eng.start()
    yield eng
    eng.close()


def _total_rss_mb(pid: int) -> float:
    """RSS of the given process plus all of its children (the V8 child
    process isn't the test process itself)."""
    proc = psutil.Process(pid)
    total = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    return total / 1024 / 1024


def test_timed_out_render_raises_and_engine_recovers(engine):
    with pytest.raises(MermaidRenderError, match="killed"):
        engine.render_svg(MINDMAP, "default", None, None)
    # the engine replaced its killed child process -- a normal render works right after
    svg = engine.render_svg(FLOWCHART, "default", None, None)
    assert svg.startswith("<svg")


def test_killed_render_does_not_leak_memory(engine):
    """The regression this whole module exists to catch: an earlier,
    thread-based version of this engine leaked ~140-160MB *every single
    time* a render timed out, since an abandoned thread's V8 isolate could
    never be reclaimed. A killed child *process* must not show that
    pattern -- total memory should stay flat across repeated timeouts."""
    pid = os.getpid()

    for _ in range(3):
        with pytest.raises(MermaidRenderError, match="killed"):
            engine.render_svg(MINDMAP, "default", None, None)
        time.sleep(0.5)  # let the OS finish reaping the killed child

    rss_after_first_batch = _total_rss_mb(pid)

    for _ in range(3):
        with pytest.raises(MermaidRenderError, match="killed"):
            engine.render_svg(MINDMAP, "default", None, None)
        time.sleep(0.5)

    rss_after_second_batch = _total_rss_mb(pid)

    # generous tolerance (not a byte-exact check) -- the point is "flat", not "growing by ~150MB x 3"
    assert rss_after_second_batch < rss_after_first_batch + 50, (
        f"memory grew from {rss_after_first_batch:.1f}MB to {rss_after_second_batch:.1f}MB "
        "across a second batch of timeouts -- looks like a leak is back"
    )


def test_normal_render_matches_quickjs_output():
    """Sanity check that the subprocess architecture didn't change what
    gets rendered: numerically equivalent to QuickJS, same as before.

    Not literal byte-equality: QuickJS's numbers ultimately come from
    novasvg's own C++ `float` (32-bit) arithmetic (via the synchronous
    Font::measureText()/etc. callback quickjs_engine.py makes -- see
    mermaidx.font_metrics), while V8's numbers come from this engine's own
    JS (64-bit double) mirror of that same math (see this module's
    docstring for why V8 needs a mirror at all). Both correctly reproduce
    the *same* underlying values -- verified independently, matching to
    many more digits than any real rendering could distinguish -- but a
    chain of individually-tiny 32-bit-vs-64-bit rounding differences
    through mermaid.js's own dagre layout math (unrelated to font
    measurement; e.g. plain "A"/"B" node labels, with no kerning pairs
    between them at all, still show this) can still leave the *last*
    couple of significant digits of a coordinate differing -- e.g.
    "178.70000076293945" vs "178.7", an absolute difference of ~7.6e-7 out
    of ~180, i.e. around one part in 235 million. A tolerance many orders
    of magnitude looser than that (down to whole pixels) still catches any
    *real* divergence (a missing/wrong kerning pair moves a coordinate by
    whole pixels, as issue history here shows) while not being sensitive
    to this float-width noise.

    One extra step beyond a plain per-number comparison: dagre's edge
    waypoints are embedded as `data-points="<base64 JSON>"`, where a
    plain-text numeric regex can't reach the numbers to give them the
    same tolerance -- decoded and compared separately below.
    """
    from mermaidx.engines.quickjs_engine import Engine as QuickJSEngine

    qjs = QuickJSEngine()
    qjs.start()
    try:
        expected = qjs.render_svg(FLOWCHART, "default", None, None)
    finally:
        qjs.close()

    v8 = Engine()
    v8.start()
    try:
        actual = v8.render_svg(FLOWCHART, "default", None, None)
    finally:
        v8.close()

    # data-points="<base64 JSON>" (dagre's own edge-routing waypoints,
    # mermaid.js's addition, not part of the SVG spec) is the one place a
    # number is encoded where a plain-text regex can't reach it: swap each
    # occurrence for a placeholder up front, in both strings, comparing
    # its *decoded* numbers (still with the same tolerance) separately,
    # so it doesn't defeat the structural/numeric comparison below.
    points_re = re.compile(r'data-points="([^"]*)"')

    def _extract_points(svg: str) -> list:
        decoded = []
        for b64 in points_re.findall(svg):
            padded = b64 + "=" * (-len(b64) % 4)
            decoded.append(json.loads(base64.b64decode(padded)))
        return decoded

    expected_points = _extract_points(expected)
    actual_points = _extract_points(actual)
    expected = points_re.sub('data-points="\0"', expected)
    actual = points_re.sub('data-points="\0"', actual)

    assert len(expected_points) == len(actual_points)
    for e_group, a_group in zip(expected_points, actual_points):
        assert len(e_group) == len(a_group)
        for e_pt, a_pt in zip(e_group, a_group):
            assert e_pt.keys() == a_pt.keys()
            for key in e_pt:
                assert a_pt[key] == pytest.approx(e_pt[key], abs=1e-3), f"{a_pt!r} != {e_pt!r} (within tolerance)"

    number_re = re.compile(r"-?\d+\.?\d*")
    expected_numbers = [float(n) for n in number_re.findall(expected)]
    actual_numbers = [float(n) for n in number_re.findall(actual)]

    # Same structure: every non-numeric token (tags, attribute names,
    # punctuation) lines up exactly -- only the numbers themselves get any
    # tolerance.
    assert number_re.sub("\0", expected) == number_re.sub("\0", actual)
    assert len(expected_numbers) == len(actual_numbers)
    for e, a in zip(expected_numbers, actual_numbers):
        assert a == pytest.approx(e, abs=1e-3), f"{a!r} != {e!r} (within tolerance)"
