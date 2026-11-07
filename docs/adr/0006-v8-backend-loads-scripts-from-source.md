# 6. The V8 backend loads its scripts from source

- Status: Open (nothing changed; options below)
- Date: 2026-11-07

## Context

V8 is much faster than QuickJS at running JavaScript once it has warmed up, and yet in the published benchmark
`js:mermaid | quickjs` has the lower median (215 ms against 305 ms) and the lower first render (716 ms against
1.06 s). The per-diagram times show where the difference comes from:

| Diagram | `quickjs` | `v8` |
| --- | --- | --- |
| `00_info` (lightest) | 91.8 ms | 229 ms |
| `12_pie_chart` | 112 ms | 247 ms |
| `24_c4_context` (heavy) | 1.83 s | 772 ms |
| `48_zenuml_control_flow` | 844 ms | 373 ms |
| `39_mindmap_shapes` | 593 ms | 450 ms |

On small diagrams the time is the cost of building the context ([ADR 0002](0002-fresh-javascript-context-per-render.md)),
and QuickJS pays about a third of what V8 pays, because it loads `mermaid.js` from bytecode
([ADR 0003](0003-load-large-scripts-from-quickjs-bytecode.md)). On heavy diagrams the running of the JavaScript
dominates and V8 is faster, which fits its JIT.

The V8 backend (`mermaidx/engines/v8_engine.py`, running `py_mini_racer` in a spawned child process) builds each context
with `ctx.eval(script)` on the source. Timed here on a slow sandbox, building one fresh context took 310 to 340 ms for
V8 (470 ms the first time) and 110 to 150 ms for QuickJS with bytecode.

What `py_mini_racer` 0.14.1, the latest on PyPI, offers: its native interface is `mr_eval`, `mr_call_function`, memory
limits, `mr_heap_stats` and `mr_heap_snapshot`. There is no V8 code cache and no startup snapshot. (`heap_snapshot`
is the heap profiler's dump for debugging memory.) V8 flags can be set once per process with `init_mini_racer(flags=...)`;
mermaidx never calls it, so V8 runs with the default `--single-threaded`. Rendering `01_simple_flowchart` and
`24_c4_context` with and without that flag gave the same times within the noise of the sandbox (about 850 to 1100 ms
and about 1400 ms either way), so the flag is not what holds V8 back.

## Decision

No change for now. V8 stays as it is, as the faster backend on heavy diagrams (`c4_context`, ZenUML, `mindmap_shapes`), and QuickJS with bytecode as the faster one on light diagrams.

## Alternatives considered

- **A V8 binding that exposes code caching or startup snapshots.** It would be expected to cut the V8 floor the way
  bytecode cut QuickJS's, which would leave V8 ahead on heavy diagrams and close on light ones. Which Python binding offers this is
  not known; it has to be found and tried, and it would replace `py_mini_racer`.
- **Reuse a V8 context across renders.** Blocked by [ADR 0002](0002-fresh-javascript-context-per-render.md).
- **Build the next context in the background after each render**, as the QuickJS engine does. It hides the cost when
  the caller has other work to do, but does not reduce it, and in a tight loop (the benchmark) nothing is hidden.
- **Change V8 flags.** Tried with `--single-threaded` removed; no measurable effect.

## Consequences

- The "which backend is faster" answer depends on the diagram, and the documentation should not claim one winner.
- Until one of the options is chosen, V8 render times keep a floor of a few hundred milliseconds that QuickJS does not
  have.
- The V8 backend also differs from QuickJS in output on some diagrams (for example `39_mindmap_shapes`, where V8's
  `Math.sin` differs by one unit in the last place); `note.md` records that, and `tests/test_mmdc_structural.py` marks
  it as a known difference.
