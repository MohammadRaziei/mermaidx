---
title: How the benchmarks work
sidebar_position: 6
description: What the benchmark page measures, how, and how to read it.
---

The [benchmark gallery](/benchmarks) renders the same 43 Mermaid files with five renderers and shows the resulting PNGs next to the time each one took. Everything on that page is produced by a CI job on every release, so nothing is typed in by hand.

## Renderers

| Renderer | How it is run |
| --- | --- |
| `@mermaid-js/mermaid-cli` | The official [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), started once per diagram. It drives headless Chrome |
| `js:mermaid \| quickjs` | `mermaidx.render(source, engine="quickjs")`, in one Python process |
| `js:mermaid \| v8` | The same with `engine="v8"` |
| `js:pele \| quickjs` | `mermaidx.render(source, backend="js:pele", engine="quickjs")` |
| `js:pele \| v8` | The same with `engine="v8"` |
| `rust:merman` | The same with `backend="rust:merman"` |
| `rust:mermaid-rs-renderer` | The same with `backend="rust:mermaid-rs-renderer"` |

## What is timed

The clock covers the work from Mermaid text to PNG bytes (to a PNG file for `mmdc`).

- **mermaidx** is called as a library, so the time excludes starting Python. It is the median of several back-to-back runs after a warm-up render. The `quickjs` and `v8` backends build a fresh engine context for every diagram, the way `mmdc` opens a new page for each one, and they prepare the next context in the background while idle. Back-to-back renders leave no idle time, so this benchmark includes that cost. The time of the very first render in a process is reported separately as start-up.
- **mmdc** is a command-line program, so each run includes starting Node.js and Chrome. This is how it is used in a build script, and it is the cost mermaidx is designed to avoid. It is the median of fewer runs, because each one is slow.

> [!caution]
> The two groups are not measuring the same thing. Compare mermaidx backends with each other directly. Compare mermaidx with `mmdc` as "per diagram in a script", not as "pure layout speed".

## Reading the results

- A cell that says **not supported** means the renderer raised an error or produced no image for that sample. These are never counted in the averages.
- Producing an image does not mean producing a correct one. A renderer may draw a diagram type it does not know as a generic picture instead of raising an error, so look at the pictures, not only at the counts.
- The speed-up written next to each bar in the first chart is the median, over the samples both renderers handled, of `mmdc` time divided by that renderer's time.
- Absolute times depend on the CI machine. The machine and every version are listed on the page, so treat the numbers as relative.
- The images are not identical. Each renderer lays out and paints text its own way, which makes the gallery useful for spotting visual differences too.

## More measurements

Under "More measurements" the page has five more charts. They are made by the same script and are left out when their data is missing.

- **Size on disk** is what installing a renderer puts on disk: for mermaidx the `mermaidx` package, `novasvg` (it writes the PNGs) and the engine (`quickjs-ng`, `mini-racer` or `mmdr`); for `mmdc` its `node_modules` and the Chromium that puppeteer downloaded. Node.js itself is not counted. The `mermaidx` package holds the JavaScript of every backend (`mermaid.js`, `pele.js`, the ELK layout and ZenUML), whichever one you use, so the `js:mermaid` and `js:pele` bars differ only by their engine. The tooltip also says how much JavaScript one render loads: all of `mermaid.js` for `js:mermaid`, much less for `js:pele`.
- **Words of the reference that were drawn** compares each mermaidx picture with the mermaid-cli reference that is kept next to the sample (`tests/samples/<name>.svg`). For every diagram it takes the words of the reference and counts how many of them the renderer's SVG has too. It does not look at layout, font or color, so it cannot tell you that a picture looks different, only that a label is missing or that the diagram was drawn as a generic picture. `js:mermaid` should be at 100%, as it is the same Mermaid. This chart is not shown for `mmdc`, which made the references.
- **First render and the ones after it** shows the startup cost: the first render of mermaidx starts its engine, the next ones do not. It is the number that counts for a script that renders one diagram and exits.
- **Rendering many diagrams in parallel** times `mermaidx.render_many()` with 1, 2, 4, ... worker processes, up to the number of cores of the machine. It renders from Mermaid text to SVG, which is the work of the workers. The diagrams are taken from the middle of the renderer's own timings (up to 8 of them, repeated to `--scaling-items`, 16 by default) so that one slow diagram does not decide the result, and every point is the median of `--scaling-repeats` runs. The speed-up cannot pass the number of cores, and on a machine with one core more workers are only slower. It is measured for `js:mermaid | quickjs` and `js:pele | quickjs`.
- **Time against the size of the diagram** has one point for every diagram and renderer: the length of the Mermaid text in characters against the time. The length is a rough size; two diagrams with the same number of characters can be very different to lay out.

## Run it yourself

Everything goes through the `Makefile` in the `docs` directory, and CI runs the same thing. Each target installs what it needs first.

```bash
cd docs
make benchmark      # writes docs/static/benchmarks/results.json and the PNGs
make serve          # browse the site with live reload
```

The first run downloads mermaid-cli and its Chromium (about 170 MB). If you only want the mermaidx backends, use `make benchmark WITH_MMDC=0`. To change how it runs, pass arguments to `benchmarks/run.py`, for example:

```bash
make benchmark BENCH_ARGS="--only 31_venn --repeats 10"
```

`--scaling-items 0` skips the parallel measurement, which is the slowest of the extras.

`make help` lists every target, and `docs/README.md` in the repository explains the whole setup.
