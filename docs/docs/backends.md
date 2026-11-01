---
title: Backends
sidebar_position: 4
description: The rendering backends, the JS engines, and when to use each.
---

Every backend sits behind the same `Diagram` API. Only `svg()` differs: PNG, JPEG, PDF, raw and NumPy output all come from the same novasvg pipeline.

A backend is named `<kind>:<name>`.

| Backend | What runs | Use it when |
| --- | --- | --- |
| `js:mermaid` (default) | The real mermaid.js | You want the reference output, or any diagram type |
| `js:pele` | [pele](https://pele.run), a small Mermaid renderer in JavaScript | You want speed (it is far faster than mermaid.js) and can accept its own layout and look, themed with CSS variables |
| `rust:merman` | Native Rust, through `mmdr` | You want no JavaScript engine at all |
| `rust:mermaid-rs-renderer` | Native Rust, an alternative renderer from `mmdr` | Same as above, with a different layout engine |

mermaidx bundles mermaid.js 12.2.0 and pele 1.13.0.

The `js:` backends run inside a JS engine, chosen with `engine=`. It is `None` unless you set it, and `None` means `quickjs`.

| Engine | What runs | Use it when |
| --- | --- | --- |
| `quickjs` (default) | QuickJS-ng | You want the zero-dependency install |
| `v8` | V8 through `mini-racer` | You render a lot and want JIT speed |

```python
import mermaidx

mermaidx.render(source)                                  # js:mermaid on quickjs
mermaidx.render(source, engine="v8")                     # js:mermaid on v8
mermaidx.render(source, backend="js:pele")
mermaidx.render(source, backend="rust:merman").pdf()
```

## js:mermaid

It runs the same, unmodified mermaid.js against a small fake DOM, on either engine, so the engines support the same diagram types and options (`theme`, `config`, `css`). The difference is the engine: V8 compiles to machine code and is faster, QuickJS is an interpreter that installs anywhere.

V8 runs in an isolated child process, so all of its memory is released when the render finishes.

One diagram, `39_mindmap_shapes`, currently renders differently on V8. See [known issues](./known-issues.md).

### ELK layout

A diagram can ask for the ELK layout instead of dagre, with `flowchart-elk`, or `layout: elk` in the frontmatter or in `config=`; `elk.stress`, `elk.force` and `elk.mrtree` work too. mermaidx loads ELK (`assets/layout_elk.js`, 2.4 MB) only for a diagram that asks for it, so the other diagrams stay as fast as before. An ELK render takes about a second longer for that reason.

```python
mermaidx.render("flowchart-elk TD\n  A --> B --> C\n  C --> A")
mermaidx.render("flowchart TD\n  A --> B", config={"layout": "elk"})
```

`js:pele` has its own layout and ignores the request.

## js:pele

pele is a separate renderer with its own layout, so its output differs from mermaid.js. It is also much faster: in our timings it renders a small diagram in a few milliseconds where `js:mermaid` takes about a second (over 100 times faster on the samples we timed). The [Benchmarks page](/benchmarks) has the measured times and every sample rendered by every backend, so you can see what the different layout looks like before you choose it. It needs no DOM, runs on either engine, and is themed with CSS variables rather than Mermaid themes: leave `theme` unset, and pass `css`, for example `css="svg{--pele-bg:#111;--pele-fg:#eee}"`. `config` is passed to pele. PNG, JPEG and PDF output need `novasvg` 0.11.4 or newer, which mermaidx requires, because pele paints with nested CSS variables.

## Rust backends

`rust:merman` and `rust:mermaid-rs-renderer` are separate reimplementations, not mermaid.js. They take `theme`, `node_spacing`, `rank_spacing` and `aspect_ratio` instead of `config` and `css`. They may not support every diagram type, and their layout can differ from mermaid.js. The [benchmark gallery](/benchmarks) shows exactly which samples each backend renders.

## Speed

Numbers depend on the machine, so the benchmark page publishes them for every sample, measured in CI on each release. See [how the benchmarks work](./benchmarks-method.md).
