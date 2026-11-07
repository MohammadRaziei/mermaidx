# quickjs-ng with bytecode

mermaidx gives every `js:mermaid` render a fresh JavaScript context, and building one is almost all parsing:
QuickJS compiles every function of a script when it loads it, so the 5.5 MB of `mermaid.js` take about 800 ms to
evaluate. The same script loaded as precompiled bytecode takes about 100 ms (measured with
[`mermaidx/engines/_bytecode.py`](../../mermaidx/engines/_bytecode.py); the numbers are in the changelog).

The `quickjs-ng` package does not let Python reach QuickJS's `JS_WriteObject` / `JS_ReadObject`. `module.c` here is
the `module.c` of `quickjs-ng` 0.18.0.1 with two methods added to `Context`, and nothing else changed:

- `compile(source: str, name: str = "<input>") -> bytes`: compiles a global script without running it and returns its
  bytecode.
- `eval_bytecode(data: bytes)`: runs such bytecode as a global script and returns the result like `eval`. It raises a
  `JSException` if the bytecode is not from the same QuickJS build.

## Use

```sh
tools/quickjs_ng_bytecode/build.sh
pip install --force-reinstall --no-deps tools/quickjs_ng_bytecode/dist/quickjs_ng-*.whl
```

Nothing else to do: mermaidx looks for the two methods and uses them when they are there. Without them it evaluates
the source, as before, so the stock `quickjs-ng` from PyPI keeps working and the output is the same either way
(`tests/test_bytecode.py` checks that, ELK and ZenUML included; it skips itself when the methods are missing).

The first render makes the bytecode (31 MB for `mermaid.js`) and keeps it in `~/.cache/mermaidx/bytecode` (or
`$XDG_CACHE_HOME`, `~/Library/Caches`, `%LOCALAPPDATA%`; `MERMAIDX_CACHE_DIR` moves it, `MERMAIDX_BYTECODE_CACHE=0`
turns the whole thing off). A file there is only used if its checksum, its QuickJS bytecode version and the checksum of
the script it was made from all match; otherwise it is made again.

## Upstream

The change is small and general, and belongs in `quickjs-ng` itself. Until it is released there, this directory is the
way to have it. When a `quickjs-ng` release has the two methods, delete this directory.

`module.c` is under the license of the package it comes from: [`licenses/quickjs-ng-MIT.txt`](../../licenses/quickjs-ng-MIT.txt).
