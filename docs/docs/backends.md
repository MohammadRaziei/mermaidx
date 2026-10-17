---
title: Backends
sidebar_position: 4
description: The four rendering backends and when to use each.
---

Every backend sits behind the same `Diagram` API. Only `svg()` differs: PNG, JPEG, PDF, raw and NumPy output all come from the same novasvg pipeline.

| Backend | What runs | Use it when |
| --- | --- | --- |
| `quickjs` (default) | The real mermaid.js in QuickJS-ng | You want the zero-dependency install, or any diagram type |
| `v8` | The real mermaid.js in V8 through `mini-racer` | You render a lot and want JIT speed |
| `merman` | Native Rust, through `mmdr` | You want no JavaScript engine at all |
| `mermaid-rs-renderer` | Native Rust, an alternative renderer from `mmdr` | Same as above, with a different layout engine |

```python
import mermaidx

mermaidx.render(source)                                  # quickjs
mermaidx.render(source, backend="v8")
mermaidx.render(source, backend="merman").pdf()
```

## quickjs and v8

Both run the same, unmodified mermaid.js against a small fake DOM, so they support the same diagram types and options (`theme`, `config`, `css`). The difference is the engine: V8 compiles to machine code and is faster, QuickJS is an interpreter that installs anywhere.

V8 runs in an isolated child process, so all of its memory is released when the render finishes.

One diagram, `39_mindmap_shapes`, currently renders differently on V8. See [known issues](./known-issues.md).

## Rust backends

`merman` and `mermaid-rs-renderer` are separate reimplementations, not mermaid.js. They take `theme`, `node_spacing`, `rank_spacing` and `aspect_ratio` instead of `config` and `css`. They may not support every diagram type, and their layout can differ from mermaid.js. The [benchmark gallery](/benchmarks) shows exactly which samples each backend renders.

## Speed

Numbers depend on the machine, so the benchmark page publishes them for every sample, measured in CI on each release. See [how the benchmarks work](./benchmarks-method.md).
