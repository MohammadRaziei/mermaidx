---
title: Known issues
sidebar_position: 8
description: Differences from mermaid-cli that are known and tracked.
---

mermaidx is checked against the output of `mmdc` 12 (mermaid-cli 12.0.0, which bundles Mermaid 12.2.0) with a strict structural XML comparison on 43 reference samples, on both the `quickjs` and `v8` engines. Numbers may differ by up to one pixel; everything else (elements, attributes, text, structure) must be equal. On Linux, 40 of the 43 samples match on `quickjs` and 39 on `v8`. The ones that do not are listed below, and each is recorded in the test suite as a strict expected failure, so the test fails loudly the day it starts to pass.

## Text is measured with one font

mermaidx lays diagrams out with the bundled DejaVu Sans, whatever font the diagram asks for. `mmdc` 12 loads its own web fonts (Recursive Variable and Open Sans) into the browser page, so a diagram rendered by a real `mmdc` on your machine measures its text with other widths, and can come out a little wider or narrower. The reference SVGs in `tests/samples` are rendered with those two web fonts switched off and DejaVu Sans forced, which is why they can be compared exactly; see `tests/samples/README.md` for the recipe.

## `24_c4_context`, `37_erd_relations` and `38_class_advanced` differ on both engines

These three come out with a different layout than in `mmdc`:

- `24_c4_context`: one label wraps onto two lines here and stays on one line in `mmdc`, so a node is 216 px wide instead of 236.7 px and the diagram 15 px taller.
- `37_erd_relations`: the entities are narrower (the diagram is 673 px wide instead of 695 px), so the edges are routed differently.
- `38_class_advanced`: the class boxes are shorter (the diagram is 394.5 px high instead of 389 px), so the edges are routed differently.

For the c4 case the cause is known. Chrome rounds a fractional font size (c4 uses 11.48 px) to a grid of about 1/64 px before it measures the text, and mermaidx measures at the exact size. The widths then differ by about 0.1 px, and where Mermaid wraps or sizes by those widths, the whole layout moves. The same kind of difference is the likely cause for the other two, but that has not been confirmed. mermaidx does not round by hand to imitate this.

## `39_mindmap_shapes` differs on V8 and on macOS

The sample differs from `mmdc` on the `v8` engine, and on `quickjs` under macOS. On Linux, `quickjs` matches `mmdc`.

The cause is a difference of one unit in the last place (1 ulp) in `Math.sin` between engine and platform builds. The mindmap layout (cose-bilkent) repeats the calculation many times, so the difference grows until the diagram comes out differently.

This is recorded in the test suite as a strict expected failure, so the test fails loudly the day it starts to pass. A deterministic `Math` layer is being considered, but it is not part of 0.11.0.

## Labels with an `<img>` fail

A label that contains an `<img>` tag makes the `js:mermaid` backend fail with `mermaid.render() produced no output (unknown error)`; `mmdc` renders the image. Mermaid waits for each image to finish loading, and mermaidx never loads images, so the wait never ends. Remove the `<img>` from the label, or draw the image another way. The other things tried in a label (entities, `<b>`, `<i>`) match `mmdc`, and `<script>` and event attributes such as `onclick` are removed, as in `mmdc`.

## ZenUML: no theme, no config, and not the same as in a browser

A `zenuml` diagram is not drawn by mermaid.js but by the SVG renderer of `@zenuml/core` (see [backends](./backends.md)), so Mermaid's `theme`, `config` and `css` do not apply to it. The `js:pele` backend does not know ZenUML. That renderer is the one of the ZenUML command line tool, not the HTML renderer of the Mermaid plugin that a browser runs, so small differences in spacing or style are possible. Only a few diagrams have been compared by eye so far.

## Rust backends

`rust:merman` and `rust:mermaid-rs-renderer` are independent implementations. They can lay out a diagram differently from mermaid.js, and may not support every diagram type. See the [benchmark gallery](/benchmarks) for the current state.

## Report a problem

Open an issue on [GitHub](https://github.com/MohammadRaziei/mermaidx/issues) with the diagram source and the versions from `mermaidx --version` and `mermaidx --info`.
