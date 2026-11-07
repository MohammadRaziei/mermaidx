"""mermaidx/engines/_bytecode.py: a fresh context loads big scripts as bytecode instead of parsing them again."""
import os
from pathlib import Path

import pytest
import quickjs

from mermaidx.engines import _bytecode, _common
from mermaidx.engines.quickjs_engine import Engine

# CI sets MERMAIDX_REQUIRE_BYTECODE=1 after installing the patched quickjs-ng, so a missing binding fails there
# instead of silently skipping the bytecode tests.
REQUIRED = bool(os.environ.get("MERMAIDX_REQUIRE_BYTECODE"))
HAS_BINDING = _bytecode.supported(quickjs.Context())
needs_binding = pytest.mark.skipif(
    not HAS_BINDING and not REQUIRED,
    reason="the installed quickjs-ng has no Context.compile / eval_bytecode (see tools/quickjs_ng_bytecode)",
)


def test_binding_is_there_when_required():
    if REQUIRED:
        assert HAS_BINDING, "MERMAIDX_REQUIRE_BYTECODE is set but quickjs-ng has no Context.compile / eval_bytecode"
SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("MERMAIDX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("MERMAIDX_BYTECODE_CACHE", raising=False)
    _bytecode._memory.clear()
    _bytecode._key.cache_clear()
    yield tmp_path
    _bytecode._memory.clear()


class _Spy:
    """A context that only counts which way a script was loaded."""

    def __init__(self, *, with_bytecode=True):
        self.calls = []
        if with_bytecode:
            self.compile = self._compile
            self.eval_bytecode = self._eval_bytecode

    def _compile(self, source, _name="<input>"):
        self.calls.append("compile")
        return b"\x01" + source.encode()

    def _eval_bytecode(self, _data):
        self.calls.append("eval_bytecode")
        return "from bytecode"

    def eval(self, _source):
        self.calls.append("eval")
        return "from source"


def test_without_the_binding_support_the_source_is_evaluated():
    ctx = _Spy(with_bytecode=False)
    assert _bytecode.run(ctx, "x" * (_bytecode.MIN_SOURCE_CHARS + 1), "big") == "from source"
    assert ctx.calls == ["eval"]


def test_a_small_script_is_evaluated_not_cached(isolated_cache):
    ctx = _Spy()
    assert _bytecode.run(ctx, "1 + 1", "small") == "from source"
    assert ctx.calls == ["eval"] and not list(isolated_cache.iterdir())


def test_the_switch_turns_bytecode_off(monkeypatch):
    monkeypatch.setenv("MERMAIDX_BYTECODE_CACHE", "0")
    ctx = _Spy()
    assert _bytecode.run(ctx, "x" * (_bytecode.MIN_SOURCE_CHARS + 1), "big") == "from source"
    assert ctx.calls == ["eval"]


@needs_binding
def test_a_script_is_compiled_once_then_read_from_memory_and_then_from_disk(isolated_cache, monkeypatch):
    monkeypatch.setattr(_bytecode, "MIN_SOURCE_CHARS", 0)
    source = "var counter = (globalThis.counter || 0) + 1; counter * 21"

    first = quickjs.Context()
    compiles = []
    real_compile = quickjs.Context.compile
    monkeypatch.setattr(quickjs.Context, "compile", lambda self, *a: (compiles.append(1), real_compile(self, *a))[1])
    assert _bytecode.run(first, source, "demo") == 21
    assert _bytecode.run(quickjs.Context(), source, "demo") == 21  # a fresh context, same bytecode
    assert len(compiles) == 2  # one for the engine tag probe, one for the script
    (cached,) = [p for p in isolated_cache.iterdir() if p.name.startswith("demo-")]

    _bytecode._memory.clear()  # a new process: only the file is left
    compiles.clear()
    assert _bytecode.run(quickjs.Context(), source, "demo") == 21
    assert compiles == [] and cached.exists()


@needs_binding
@pytest.mark.parametrize("damage", ["truncate", "flip", "magic", "empty"])
def test_a_damaged_cache_file_is_made_again_and_never_run(isolated_cache, monkeypatch, damage):
    monkeypatch.setattr(_bytecode, "MIN_SOURCE_CHARS", 0)
    source = "6 * 7"
    assert _bytecode.run(quickjs.Context(), source, "demo") == 42
    (path,) = [p for p in isolated_cache.iterdir() if p.name.startswith("demo-")]
    raw = bytearray(path.read_bytes())
    if damage == "truncate":
        raw = raw[: len(raw) // 2]
    elif damage == "flip":
        raw[-3] ^= 0xFF
    elif damage == "magic":
        raw[0] ^= 0xFF
    else:
        raw = bytearray()
    path.write_bytes(bytes(raw))

    _bytecode._memory.clear()
    assert _bytecode.run(quickjs.Context(), source, "demo") == 42
    assert _bytecode._read(path) is not None  # the file is good again


@needs_binding
def test_the_file_of_an_older_source_is_removed(isolated_cache, monkeypatch):
    monkeypatch.setattr(_bytecode, "MIN_SOURCE_CHARS", 0)
    _bytecode.run(quickjs.Context(), "1", "demo")
    _bytecode.run(quickjs.Context(), "2", "demo")
    _bytecode.run(quickjs.Context(), "3", "other")
    names = sorted(p.name.split("-")[0] for p in isolated_cache.iterdir())
    assert names == ["demo", "other"]


@needs_binding
@pytest.mark.parametrize("through", ["bytecode", "source"])
def test_an_error_thrown_by_the_script_is_the_scripts_own(monkeypatch, through):
    monkeypatch.setattr(_bytecode, "MIN_SOURCE_CHARS", 0 if through == "bytecode" else 10**9)
    with pytest.raises(quickjs.JSException, match="boom"):
        _bytecode.run(quickjs.Context(), "throw new Error('boom')", "demo")


@needs_binding
def test_a_script_that_does_not_compile_fails_like_eval_would(monkeypatch):
    monkeypatch.setattr(_bytecode, "MIN_SOURCE_CHARS", 0)
    with pytest.raises(quickjs.JSException, match="SyntaxError"):
        _bytecode.run(quickjs.Context(), "var = ;", "demo")


# -- what the engine draws does not depend on how its scripts were loaded ----------------------------------------------


def _render(code, library="mermaid", config=None):
    engine = Engine(library)
    engine.start()
    try:
        return engine.render_svg(code, None, config, None)
    finally:
        engine.close()


_ELK = "flowchart-elk TD\n  A[Start] --> B{Choice}\n  B -->|yes| C[One]\n  B -->|no| D[Two]\n"
_ZENUML = "zenuml\n  title Order\n  Client->Server.get() {\n    Server->DB.query()\n  }\n"


@needs_binding
@pytest.mark.parametrize(
    "name, code",
    [(n, None) for n in ("01_simple_flowchart", "03_simple_sequence", "12_pie_chart", "13_gantt")]
    + [("elk", _ELK), ("zenuml", _ZENUML)],
)
def test_the_engine_draws_the_same_through_bytecode_and_through_source(name, code, monkeypatch):
    if code is None:
        code = (SAMPLES / f"{name}.mmd").read_text(encoding="utf-8")
    through_bytecode = _render(code)
    monkeypatch.setenv("MERMAIDX_BYTECODE_CACHE", "0")
    through_source = _render(code)
    assert through_bytecode == through_source
    assert "<svg" in through_bytecode


def test_library_scripts_name_what_a_diagram_needs_on_top_of_the_context():
    assert _common.library_scripts("flowchart LR; A-->B") == ()
    assert [n for n, _ in _common.library_scripts("flowchart-elk LR; A-->B")] == ["layout_elk"]
    assert [n for n, _ in _common.library_scripts("zenuml\n  A.m()")] == ["zenuml"]
    assert _common.library_scripts("flowchart-elk LR; A-->B", None, "pele") == ()
    # the engine that loads them itself gets a script without them, the other engine the whole thing as before
    whole = _common.render_script("flowchart-elk LR; A-->B", None, None, None)
    bare = _common.render_script("flowchart-elk LR; A-->B", None, None, None, with_libraries=False)
    assert len(whole) > 1_000_000 > len(bare)
