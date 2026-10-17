---
title: How the benchmarks work
sidebar_position: 6
description: What the benchmark page measures, how, and how to read it.
---

The [benchmark gallery](/benchmarks) renders the same 43 Mermaid files with five renderers and shows the resulting PNGs next to the time each one took. Everything on that page is produced by a CI job on every release, so nothing is typed in by hand.

## Renderers

| Renderer | How it is run |
| --- | --- |
| `mmdc` | The official [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), started once per diagram. It drives headless Chrome |
| `mermaidx quickjs` | `mermaidx.render(source, backend="quickjs")`, in one Python process |
| `mermaidx v8` | The same with `backend="v8"` |
| `mermaidx merman` | The same with `backend="merman"` |
| `mermaidx mermaid-rs-renderer` | The same with `backend="mermaid-rs-renderer"` |

## What is timed

The clock covers the work from Mermaid text to PNG bytes (to a PNG file for `mmdc`).

- **mermaidx** is called as a library, so the time excludes starting Python. It is the median of several back-to-back runs after a warm-up render. The `quickjs` and `v8` backends build a fresh engine context for every diagram, the way `mmdc` opens a new page for each one, and they prepare the next context in the background while idle. Back-to-back renders leave no idle time, so this benchmark includes that cost. The time of the very first render in a process is reported separately as start-up.
- **mmdc** is a command-line program, so each run includes starting Node.js and Chrome. This is how it is used in a build script, and it is the cost mermaidx is designed to avoid. It is the median of fewer runs, because each one is slow.

:::caution
The two groups are not measuring the same thing. Compare mermaidx backends with each other directly. Compare mermaidx with `mmdc` as "per diagram in a script", not as "pure layout speed".
:::

## Reading the results

- A cell that says **not supported** means the renderer raised an error or produced no image for that sample. These are never counted in the averages.
- Producing an image does not mean producing a correct one. A renderer may draw a diagram type it does not know as a generic picture instead of raising an error, so look at the pictures, not only at the counts.
- The speed-up written next to each bar in the first chart is the median, over the samples both renderers handled, of `mmdc` time divided by that renderer's time.
- Absolute times depend on the CI machine. The machine and every version are listed on the page, so treat the numbers as relative.
- The images are not identical. Each renderer lays out and paints text its own way, which makes the gallery useful for spotting visual differences too.

## Run it yourself

Everything goes through the `Makefile` in the repository root, and CI runs the same targets.

```bash
make install-python install-mmdc    # mermaidx with every backend, and mermaid-cli
make benchmark                      # writes docs/static/benchmarks/results.json and the PNGs
make serve                          # browse the site with live reload
```

Skip `make install-mmdc` if you do not have Node.js: the benchmark then runs without `mmdc`. To change how it runs, pass arguments to `benchmarks/run.py`, for example:

```bash
make benchmark BENCH_ARGS="--only 31_venn --repeats 10"
```

`make help` lists every target.
