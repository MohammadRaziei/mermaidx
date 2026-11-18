# 7. Depend on a `quickjs-ng` that has the bytecode methods

- Status: Accepted
- Date: 2026-11-18

## Context

[ADR 0004](0004-ship-bytecode-methods-through-quickjs-ng-upstream.md) kept a patched build of `quickjs-ng` in
`tools/quickjs_ng_bytecode/` until a release had `Context.compile` and `Context.eval_bytecode`. The pull request
[`genotrance/quickjs-ng#22`](https://github.com/genotrance/quickjs-ng/pull/22) was merged, and `quickjs-ng` 0.18.0.2
is on PyPI. Its `cp310-abi3` manylinux x86_64 wheel was downloaded and checked: `hasattr(quickjs.Context, "compile")`
and `hasattr(quickjs.Context, "eval_bytecode")` are both true.

The same wheel declares `Requires-Python: >=3.10`, and mermaidx declares `>=3.9`.

## Decision

- `pyproject.toml` asks for `quickjs-ng>=0.18.0.2` on Python 3.10 and newer, and keeps `quickjs-ng>=0.15.1` on 3.9
  (environment markers). On 3.9 mermaidx works as before, without bytecode ([ADR 0003](0003-load-large-scripts-from-quickjs-bytecode.md)).
- `tools/quickjs_ng_bytecode/`, `licenses/quickjs-ng-MIT.txt` and the `NOTICES.md` entry are deleted: mermaidx ships no
  QuickJS code.
- CI (`wheel.yml`) and `docs/Makefile` install nothing extra any more, and `WITH_BYTECODE` is gone. CI still sets
  `MERMAIDX_REQUIRE_BYTECODE=1`, now with the stock package.
- The run-time check in `_bytecode.py` and the skip in `tests/test_bytecode.py` stay, for 3.9.

## Alternatives considered

- **Keep the patched build.** It would be a second copy of `module.c` to keep in step with upstream, for nothing.
- **A plain `quickjs-ng>=0.18.0.2` without markers.** `pip install mermaidx` would fail to resolve on Python 3.9.
- **Raise `requires-python` to 3.10.** It drops 3.9 users for a speed feature that mermaidx can do without. Not done.

## Consequences

- `pip install mermaidx` on Python 3.10 and newer gets the bytecode path; on 3.9 the output is the same, only slower.
- CI no longer needs a C compiler to build QuickJS, and the Windows job no longer depends on `build.sh` under Git Bash.
- Not checked when this was written: the test suite and the benchmark with the PyPI wheel, the macOS and Windows
  wheels, and Python 3.9 resolution.
- Revisit when 3.9 is dropped: remove the second requirement line and the markers.
- Records 0001, 0003, 0004 and 0005 still name `tools/quickjs_ng_bytecode/`; they are history and are not rewritten.
