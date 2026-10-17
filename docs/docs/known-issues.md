---
title: Known issues
sidebar_position: 8
description: Differences from mermaid-cli that are known and tracked.
---

mermaidx is checked against the output of `mmdc` with a strict structural XML comparison on 43 reference samples, on both the `quickjs` and `v8` engines. Only floating point values have a tolerance. 42 of the 43 samples match.

## `39_mindmap_shapes` differs on V8 and on macOS

The sample differs from `mmdc` on the `v8` backend, and on `quickjs` under macOS. On Linux, `quickjs` matches `mmdc`.

The cause is a difference of one unit in the last place (1 ulp) in `Math.sin` between engine and platform builds. The mindmap layout (cose-bilkent) repeats the calculation many times, so the difference grows until the diagram comes out differently.

This is recorded in the test suite as a strict expected failure, so the test fails loudly the day it starts to pass. A deterministic `Math` layer is being considered, but it is not part of 0.10.0.

## Rust backends

`merman` and `mermaid-rs-renderer` are independent implementations. They can lay out a diagram differently from mermaid.js, and may not support every diagram type. See the [benchmark gallery](/benchmarks) for the current state.

## Report a problem

Open an issue on [GitHub](https://github.com/MohammadRaziei/mermaidx/issues) with the diagram source and the versions from `mermaidx --version` and `mermaidx --info`.
