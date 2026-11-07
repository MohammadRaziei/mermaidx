# 5. CI and the published benchmarks run the bytecode path

- Status: Accepted
- Date: 2026-11-07

## Context

Because of [ADR 0004](0004-ship-bytecode-methods-through-quickjs-ng-upstream.md), the `quickjs-ng` that
`pip install -e ".[all]"` puts in CI has no `compile` or `eval_bytecode`. Two things followed:

- 15 tests in `tests/test_bytecode.py` skipped themselves in every CI run, so the bytecode path, the cache
  and its failure handling were never tested there.
- The benchmarks on the documentation site were measured with the stock package, so they did not show what
  `js:mermaid | quickjs` can do.

## Decision

- The test job of `.github/workflows/wheel.yml` builds the patched wheel with
  `bash tools/quickjs_ng_bytecode/build.sh`, installs it over the stock one (`pip install --force-reinstall
  --no-deps`), checks that both methods exist, and runs the tests with `MERMAIDX_REQUIRE_BYTECODE=1`. With that
  variable `tests/test_bytecode.py` fails when the binding has no bytecode methods instead of skipping its tests.
  Without it (a local run on the stock package) the tests still skip.
- `docs/Makefile` does the same inside its virtualenv after installing mermaidx, so `make all` (the benchmark and the
  site, as CI runs it) measures with bytecode. `make all WITH_BYTECODE=0` keeps the stock package.
- `build.sh` is not executable in the repository, so both call it through `bash`.

## Alternatives considered

- **Leave CI on the stock package.** Simplest, and the feature would stay untested where it matters.
- **A separate CI job only for bytecode.** It would test the path but leave the benchmark numbers and the main test
  run on the stock package, so two configurations would drift.
- **Install the fork directly (`pip install git+https://github.com/MohammadRaziei/quickjs-ng@devel`).** Not tried, and
  the fork has a nested `test262` submodule that may slow or break the install.

## Consequences

- CI needs a C compiler on every runner and spends the time of a QuickJS build. At the time of writing the build, the
  bytecode tests and the full test suite had been run on Linux only; the `macos-latest` and `windows-latest` jobs were
  not run, and the Windows one is the likeliest to need a fix (`build.sh` runs under Git Bash there).
- The numbers on the benchmark page are those of a bytecode build, which a plain `pip install mermaidx` does not give
  until [ADR 0004](0004-ship-bytecode-methods-through-quickjs-ng-upstream.md) is resolved. The method page says which
  build was used.
- Some V8 tests (`[v8]` cases in `test_layout_elk.py` and `test_mmdc_structural.py`) failed with "Render exceeded
  8000 ms" in a full parallel run (`-n 4`) on a slow sandbox, and passed when the `[v8]` cases were run on their own. They
  do not use QuickJS, and whether the same happens on CI runners is not known.
