"""A long chain is a deep recursion inside mermaid.js (dagre walks it depth-first).
A browser gives the page a stack large enough for it; the default backend must too."""
import pytest

import mermaidx


def _chain(n: int) -> str:
    lines = ["flowchart TD"]
    lines += [f"  N{i}[Node {i}] --> N{i + 1}[Node {i + 1}]" for i in range(n - 1)]
    return "\n".join(lines)


@pytest.mark.parametrize("n", [150])
def test_long_chain_renders_with_default_backend(n):
    svg = mermaidx.render(_chain(n), config={"handDrawnSeed": 1}).svg()
    assert svg.startswith("<svg")
    assert f">Node {n - 1}<" in svg


def test_start_does_not_leave_a_process_wide_thread_stack_size_behind():
    import threading

    from mermaidx.engines.quickjs_engine import Engine

    before = threading.stack_size()
    engine = Engine()
    engine.start()
    try:
        assert threading.stack_size() == before
    finally:
        engine.close()


def test_runaway_recursion_is_a_js_rangeerror_not_a_crash():
    """The JS stack limit has to sit below the worker thread's real stack."""
    import quickjs

    from mermaidx.engines.quickjs_engine import Engine

    engine = Engine()
    engine.start()
    try:
        def run():
            return engine._ctx.eval("(function f(n){ return f(n + 1) + 1; })(0)")

        with pytest.raises(quickjs.JSException, match="stack"):
            engine._executor.submit(run).result()
    finally:
        engine.close()
