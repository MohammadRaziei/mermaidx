# Architecture decision records

Short notes on decisions that shaped mermaidx: what the situation was, what was chosen, what else was considered and
what follows from it. [`architecture.md`](../../architecture.md) explains how the code works; these records explain why
some of it is the way it is.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-fresh-javascript-context-per-render.md) | Every `js:mermaid` render gets a fresh JavaScript context | Accepted |
| [0003](0003-load-large-scripts-from-quickjs-bytecode.md) | Load the large scripts from cached QuickJS bytecode | Accepted |
| [0004](0004-ship-bytecode-methods-through-quickjs-ng-upstream.md) | Get `compile` / `eval_bytecode` into `quickjs-ng` upstream; keep a patched build meanwhile | Accepted (interim) |
| [0005](0005-ci-and-benchmarks-run-the-bytecode-path.md) | CI and the published benchmarks run the bytecode path | Accepted |
| [0006](0006-v8-backend-loads-scripts-from-source.md) | The V8 backend loads its scripts from source | Open |

## Writing one

Copy [`template.md`](template.md) to `NNNN-short-title.md` with the next number and add a row above. Write an ADR when a
choice is hard to undo, changes what users or CI get, or has rejected alternatives that people will ask about again.
Do not rewrite an accepted record to fit a later change: write a new one that says it supersedes the old, and change
only the old one's status line.
