# 3. Load the large scripts from cached QuickJS bytecode

- Status: Accepted
- Date: 2026-11-07 (records `mermaidx/engines/_bytecode.py`)

## Context

[ADR 0002](0002-fresh-javascript-context-per-render.md) means every render builds a context and loads `mermaid.js`
(5.5 MB) into it. QuickJS compiles every function of a script when it loads it, so this is almost all parsing: 600 to
800 ms to evaluate the source, of which running the script's top level is a few milliseconds. The same script loaded as
precompiled bytecode takes about 100 ms. (Figures from the module docstring and `tools/quickjs_ng_bytecode/README.md`;
a fresh context with bytecode took 110 to 150 ms in a run on a slow sandbox for this record.)

QuickJS can write a compiled script out (`JS_WriteObject`) and read it back (`JS_ReadObject`).

## Decision

Scripts of at least `MIN_SOURCE_CHARS` (200,000 characters) are loaded through `_bytecode.run(ctx, source, name)`,
which uses bytecode when the QuickJS binding has `Context.compile` and `Context.eval_bytecode`, and otherwise does
exactly what `ctx.eval(source)` does.

- The bytecode is made once by the first context that needs it, kept in memory and in a file under the user's cache
  directory (`~/.cache/mermaidx/bytecode`, `$XDG_CACHE_HOME`, `~/Library/Caches`, `%LOCALAPPDATA%`), so that the next
  process starts with it. `MERMAIDX_CACHE_DIR` moves the files.
- A file is named `<script>-<key>.qbc`. The key is a SHA-256 of the engine tag (the `quickjs-ng` package version and the
  bytecode version byte the compiler writes) and of the script's source, so a different QuickJS or a different script
  never finds a file that is not its own.
- A file starts with a magic string and the SHA-256 of its own payload. A file that fails any check is ignored and made
  again; bytecode that was not made by this QuickJS is never run.
- Files are written beside the target and renamed into place, so another process never reads half of one. Files of
  older sources of the same script are removed. A cache that cannot be written only makes things slower.
- `MERMAIDX_BYTECODE_CACHE=0` turns the whole thing off.

## Alternatives considered

- **Keep parsing the source on every render.** 600 to 800 ms for each diagram on QuickJS, slower than the V8 backend,
  which loads the same source in about 310 to 340 ms in the same sandbox.
- **Reuse one context for many renders.** Rejected in ADR 0002.
- **Switch to V8 for speed.** V8 is faster on heavy diagrams but has no way to cache compiled code through
  `py_mini_racer` (see [ADR 0006](0006-v8-backend-loads-scripts-from-source.md)), so QuickJS with bytecode is faster
  on light ones.

## Consequences

- With the methods present, the median `js:mermaid | quickjs` render in the published benchmark is 215 ms, against
  305 ms for V8; the first render in a new process still has to make the cache. In a run on a slow sandbox a simple
  diagram took 1.45 s with an empty cache and 0.40 s with a warm one.
- The cache is about 31 MB for `mermaid.js` and about 1.5 MB for ZenUML.
- Output does not depend on which path was used: `tests/test_bytecode.py` checks that, ELK and ZenUML included.
- **The cache holds code that will be run.** The checksum protects against damaged and stale files, not against someone
  who can write to the cache directory, because the checksum is stored in the file and is not a signature. The cache
  directory should be treated like any directory of executable code, and bytecode from anywhere else must never be
  loaded.
- The feature only exists where the binding has the two methods; see
  [ADR 0004](0004-ship-bytecode-methods-through-quickjs-ng-upstream.md).
