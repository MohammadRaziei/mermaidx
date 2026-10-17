# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/) (while below 1.0, a minor bump may carry breaking changes).

## [0.10.0] - 2026-10-17

The theme of this release is **browser-faithful output**: the DOM/SVG shim now reproduces what Chrome
does (CSSOM serialization, `getBBox`, float32 path parsing) instead of the SVG being patched afterwards,
and the SVGs are checked against `mmdc` reference output with a strict structural XML comparison.
It also moves rasterization to novasvg only and adds JPEG, BMP and TGA output.

### Added

- **JPEG, BMP and TGA output.** `Diagram.jpg()`, `.bmp()` and `.tga()`, `.save()` by extension
  (`.jpg`, `.jpeg`, `.bmp`, `.tga`), and the new top-level functions `svg_to_jpg` and `svg_to_image`.
  All encoders come from novasvg, so there is no Pillow dependency.
- **CLI:** `-o` accepts the new extensions, and `--quality N` sets the JPEG quality (1-100, default 90).
  JPEG has no transparency, so the background defaults to white for it.
- **`mermaidx/assets/path_bbox.js`:** a port of Blink's float32 SVG number parser and tight path bounding
  box (Chrome/Skia behaviour), shared by the DOM shim. Used with `Math.fround` when converting units and
  accumulating positions.
- **Shared engine code** in `mermaidx/engines/_common.py`, so the `quickjs` and `v8` engines no longer
  duplicate setup logic.
- **Structural comparison against `mmdc`:** 43 reference samples in `tests/samples/` and
  `tests/test_mmdc_structural.py`, run on both `quickjs` and `v8`. The comparison is a strict XML
  structure check (`tests/svg_compare.py`, built on `pygixml`); only floating point values have a
  tolerance. It covers the whole document, including the prolog, comments and CDATA.
- New test modules for the DOM shim, selector engine, text and shape bounding boxes, path bbox, label
  stacking, deep graphs, sanitization, and the V8 mirror and `foreignObject` paths.

### Changed

- **novasvg is now the only rasterizer** and the only text and HTML-label measurer. `novasvg>=0.7.5` is
  required (it provides the in-memory image encoders, `<foreignObject>` soft-wrapping driven by the HTML's
  own `white-space`, and GSUB f-ligature handling). mermaid.js's default HTML labels are used again
  (`htmlLabels: true`), and the global `htmlLabels` override was removed from the engine base configs.
- **DOM shim, CSS:** style handling now follows Chrome's CSSOM. Rule text is canonicalized (property
  names lowercased, `!important` handled, hex/HSLA colors converted to `rgb()`/`rgba()`, numbers to six
  significant figures, bare `font-size` numbers get `px`, whitespace after commas normalized). Multi-value
  declarations that Chrome rejects are skipped, `display: none` elements are excluded from layout, and
  redundant style rewrites are skipped.
- **DOM shim, selectors and serialization:** the selector engine handles descendant, child, adjacent and
  general-sibling combinators plus `:not` and `:first-child`. `cloneNode` materializes pending styles first,
  and `innerHTML` supports XML namespaces. HTML entities are decoded and serialized correctly, and
  `setAttributeNS` and `removeAttribute` now track namespaced attributes.
- **DOM shim, geometry:** `getBBox` on `<text>` uses the ink extent like Chrome, `foreignObject` boxes
  match the sizes novasvg paints (so content near the canvas edge is no longer clipped), and relative
  CSS units (`em`, `ex`, `rem`, `%`, `pt`) resolve to pixels.
- **V8 engine:** `foreignObject` labels are measured through a JS mirror and rendered in as many passes
  as needed until sizes settle (an error is raised after a fixed maximum). Timeouts kill the child process
  rather than a thread. The README no longer quotes specific JIT speedup figures.
- Dependencies: `termaid` is no longer version-pinned.
- Test dependencies now include `pygixml`.

### Removed (breaking)

- **Font embedding.** `Diagram.svg(embed_font=...)`, the `embed_font=` argument of `save()`, the CLI flag
  `--embed-font`, the `mermaidx[embed]` extra (and `fonttools` from `mermaidx[all]`), and
  `mermaidx/font_embed.py` are gone.
- **resvg.** `resvg_py` is no longer a dependency, and `raster="resvg"` now raises a `ValueError` with a
  migration hint. Drop the argument to use novasvg.
- **Post-render SVG patching.** `mermaidx/engines/_svg_patches.py` was deleted. The shim now produces the
  expected output directly; the journey/timeline task text color is no longer fixed up on the finished SVG.

### Known issues

- **`39_mindmap_shapes` differs from `mmdc` on `v8`, and on `quickjs` under macOS.** The cause is
  last-bit (1 ulp) differences in `Math.sin` and related functions between engine and platform builds,
  which accumulate in the cose-bilkent layout. On Linux, `quickjs` matches `mmdc` for this sample. The
  other 42 samples match on both engines, as far as Linux has been measured. This is recorded as a strict
  expected failure in the test suite, with details in `note.md`. A deterministic `Math` layer is under
  consideration but not part of this release.

[0.10.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.5...v0.10.0