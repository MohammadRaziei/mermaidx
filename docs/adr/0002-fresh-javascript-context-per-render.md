# 2. Every `js:mermaid` render gets a fresh JavaScript context

- Status: Accepted
- Date: 2026-11-07 (records a decision already in the code: `mermaidx/engines/_common.py`, `quickjs_engine.py`)

## Context

`mermaid.js` keeps state at module level, for example the id counters that name the actors of a sequence diagram
(`actor1`, `actor2`, ...) and the ids of the class diagram (`classId-N-M`), and a random sequence. A browser starts them from zero on every
page load, and mermaid-cli opens a new page for each diagram. A JavaScript context that has already rendered a diagram
numbers the ids of the next one on from where the last one stopped, so the SVG differs from what mermaid-cli produces
for the same source.

mermaidx aims to produce the same pictures as mermaid-cli, and `tests/test_mmdc_structural.py` compares the two.

## Decision

For the `mermaid` library every render runs in a context that has not rendered anything yet
(`Engine._ensure_fresh_context` on the QuickJS side, a context built by `_build_context` inside the child process on
the V8 side). The QuickJS engine builds the next context right after a render finishes, off the caller's path, so the
caller does not wait for it when it has other work to do.

`js:pele` is different: `reuses_context("pele", n)` lets one context render up to `CONTEXT_REUSE_LIMIT` (1000)
diagrams, after which it is replaced (as it is after a render that failed). pele keeps nothing between renders: all 43
samples of `tests/samples` give byte-for-byte the same SVG in one context as in a fresh one each, which
`tests/test_engine_common.py` checks on both engines. mermaid.js is different: besides the id counters it keeps a
random sequence between renders.

## Alternatives considered

- **One long-lived context, with the state reset between renders.** It would remove the cost of loading
  `mermaid.js` for every render. The reset would have to find every counter in `mermaid.js` and in each diagram module,
  and a missed one changes ids in the output. It was not attempted.
- **A pool of contexts reused in turn.** Same state problem, and more memory.

## Consequences

- Every render pays for building a context. For `mermaid.js` (5.5 MB) that is almost all parsing, which is the problem
  [ADR 0003](0003-load-large-scripts-from-quickjs-bytecode.md) addresses for QuickJS and
  [ADR 0006](0006-v8-backend-loads-scripts-from-source.md) records as open for V8.
- That cost is a floor under the time of every diagram, however small. In the published benchmark the lightest
  diagrams take about 90 ms on `js:mermaid | quickjs` and about 230 ms on `js:mermaid | v8`, which is that floor.
- If a way to reset `mermaid.js` state is ever found and tested against mermaid-cli for every diagram type, this
  decision can be revisited and would be superseded by a new record.
