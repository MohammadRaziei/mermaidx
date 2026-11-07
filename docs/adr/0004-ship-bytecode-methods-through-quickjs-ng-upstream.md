# 4. Get `compile` / `eval_bytecode` into `quickjs-ng` upstream; keep a patched build meanwhile

- Status: Accepted (interim)
- Date: 2026-11-07

## Context

[ADR 0003](0003-load-large-scripts-from-quickjs-bytecode.md) needs two methods on `quickjs.Context` that the
`quickjs-ng` package on PyPI does not have: `compile(source, name)` and `eval_bytecode(data)`. They are small wrappers
over `JS_WriteObject` and `JS_ReadObject`, which the QuickJS engine already provides.

The Python binding and the engine are in different repositories. The binding (`module.c`, `setup.py`,
`pyproject.toml`, with the engine as the submodule `upstream-quickjs`) is
[`genotrance/quickjs-ng`](https://github.com/genotrance/quickjs-ng); the engine is `quickjs-ng/quickjs`. The change
belongs in the binding.

## Decision

1. The two methods are added to `module.c` of the binding (66 added lines, nothing else changed), with type stubs,
   tests (`tests/test_bytecode.py` in that repository) and documentation, and proposed to `genotrance/quickjs-ng` as a
   pull request against `devel`. The work is on the fork `MohammadRaziei/quickjs-ng`.
2. Until a `quickjs-ng` release has them, `tools/quickjs_ng_bytecode/` keeps the same `module.c` and a `build.sh` that
   builds a wheel from the sdist of `quickjs-ng` 0.18.0.1 with it. The package name and import name stay
   `quickjs-ng` and `quickjs`.
3. mermaidx finds out at run time whether the methods are there and works without them
   ([ADR 0003](0003-load-large-scripts-from-quickjs-bytecode.md)), so its dependency stays `quickjs-ng>=0.15.1`.

## Alternatives considered

- **Publish a renamed fork of the binding on PyPI and depend on it.** The import name would still be `quickjs`, so
  installing it next to `quickjs-ng` makes the two overwrite each other's files, and every other package that needs
  `quickjs-ng` would conflict with mermaidx. It also puts a second package to maintain on the project.
- **Compile a private extension into the mermaidx wheel**, under a name of its own such as `mermaidx._qjs`. It needs
  no help from upstream and gives every user bytecode, but mermaidx stops being a pure-Python wheel: one wheel per
  platform and Python version (for example with `cibuildwheel`) and the whole of QuickJS bundled. Not done; it is the
  fallback if the upstream change does not happen.
- **Fork the engine repository (`quickjs-ng/quickjs`).** It is the wrong layer: the engine needs no change, and the
  binding is not in it.
- **Drop the feature.** `js:mermaid` on QuickJS would go back to 600 to 800 ms of loading per render.

## Consequences

- A user who runs `pip install mermaidx` gets the stock `quickjs-ng` and therefore no bytecode, until a release of
  `quickjs-ng` has the methods. Their output is the same, only slower.
- The wheel mermaidx publishes is unchanged by any of this: it holds no QuickJS code and depends on PyPI's
  `quickjs-ng`.
- Bytecode is valid only for the QuickJS build that wrote it; `eval_bytecode` raises `JSException` for anything else,
  and mermaidx keys its cache by the package version and the bytecode version byte.
- **When to revisit:** once a `quickjs-ng` release has both methods, raise the minimum version in `pyproject.toml`,
  delete `tools/quickjs_ng_bytecode/` and its licence entry if nothing else uses it, and drop the skip in
  `tests/test_bytecode.py`. If the pull request is rejected or stalls, choose between the renamed fork and the private
  extension with a new record.
