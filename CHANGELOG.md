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
  box (Chrome/Skia behavior), shared by the DOM shim. Used with `Math.fround` when converting units and
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

## [0.9.5] - 2026-08-31

### Fixed

- **Journey and timeline diagrams** no longer render with invisible labels: text placement and the task
  text color are now handled correctly (#31).
- HTML entities in text content are decoded, and the text-sanitization gap is documented in
  `architecture.md`.
- ASCII output always ends with a trailing newline.

### Changed

- The V8 install hint now points to the `mermaidx[v8engine]` extra.
- Added SVG patch tests for mindmap label centering, and clarified the backend performance footnotes
  in the README.

## [0.9.4] - 2026-07-24

### Added

- `CSS.supports` (color validation), `URL` and `compareDocumentPosition` polyfills, and
  `Node.previousSibling` in the DOM shim, which d3's `.lower()` relies on.
- `Node.toJSON()` and circular-reference handling in `JSON.stringify`, fixing block diagrams with nested
  `block:ID` groups (#23).
- Backend comparison table in the README.

### Changed

- Updated the bundled mermaid.js to **v11.16.0**.
- Font property resolution now follows CSS class rules, so elements such as diagram titles inherit
  their styling correctly.
- V8 backend detection uses `py_mini_racer`.
- README: renamed the project heading to MermaidX and restructured the installation section.

## [0.9.3] - 2026-07-20

### Added

- `embed_font` option for browser-accurate SVGs.
- `tests/test_dom_shim.py`, covering mermaid.js text-position helpers.

### Fixed

- Multi-line text positioning (#17).
- Regressions in treemap and venn diagrams (#19, #21).
- DOM shim: `Node` append/prepend and style serialization.

### Changed

- Improved text position resolution in the DOM shim.

## [0.9.2] - 2026-07-19

### Added

- **SVG font embedding.** The `--embed-font` CLI option and `embed_Dejavu_font()` embed the exact DejaVu
  Sans glyphs used as `@font-face` rules, which fixes wrong text metrics when an SVG is opened directly
  in a browser (#12). Requires `fonttools` via the new `mermaidx[embed]` extra.
- `Intl` global in the DOM shim, for grapheme splitting in multi-line node labels.

## [0.9.1] - 2026-07-18

### Added

- `screen` object in the DOM shim.

## [0.9.0] - 2026-07-18

### Added

- **V8 engine** (`mini-racer`) as an optional, selectable backend. It runs in an isolated child process so
  that memory is fully reclaimed.
- CLI quiet mode (`-q`).
- Architecture documentation (`architecture.md`) and a Google Colab badge in the README.

### Fixed

- Multi-line node labels are sized so their lines no longer overflow the box.
- Gantt chart rendering.

## [0.8.3] - 2026-07-15

### Changed

- DOM shim: CSS rule parsing and property resolution, plus additional DOM properties and methods.
- Mindmap node label centering in the SVG output.
- Added pixel-level label positioning checks to the sample tests.
- Docs: clarified the `mmdc` to `mermaidx` rename and the `pip install` variants; updated the Jupyter demo.

## [0.8.2] - 2026-07-12

### Added

- DOM shim: a minimal `CSSStyleSheet`, `TextEncoder`/`TextDecoder`, `btoa`/`atob` polyfills and
  `text-anchor` support.

### Changed

- Updated the bundled mermaid.js.
- Improved text positioning and bounding-box calculation in the DOM shim.

## [0.8.1] - 2026-07-12

### Added

- Jupyter support and examples: a `Diagram` displays automatically as the last expression in a cell.
- `tests/samples` and regression tests for Mermaid source files.
- `RegExp` and `crypto` polyfills in the DOM shim, for mermaid.js compatibility.

## [0.8.0] - 2026-07-10

### Changed (breaking)

- **Rebranded from `mmdc` to `mermaidx`.** The Python package and the module are now named `mermaidx`;
  install it with `pip install mermaidx`.

## [0.7.0] - 2026-07-10

### Changed

- Final release under the `mmdc` name: it adds a deprecation notice in the README and in `__init__.py`
  pointing to `mermaidx`.
- `numpy` was added to the `all` extra and the package description was updated.

## [0.6.2] - 2026-07-09

### Added

- **Backend selection** via `backend=`.
- `DiagramBase` as the shared base class for all backends, and `DiagramRust` for the optional `mmdr`
  backends, with PDF, raw and numpy output available for every backend.

### Fixed

- Removed a leftover debug log from `dom_shim.js`.

## [0.6.1] - 2026-07-08

### Added

- **ASCII output.**

### Changed

- README improvements.

## [0.6.0] - 2026-07-08

### Added

- **`Diagram` class and `render()` function**, with lazy and cached output methods.
- Optional Rust dependency (`mmdr`) and online comparison tests.

### Changed

- **No more PhantomJS.** Phasma was removed; rendering now runs mermaid.js in an embedded QuickJS engine
  with a DOM shim, and rasterizes with resvg.
- The Docusaurus documentation site was removed from the repository.

## [0.5.0] - 2026-06-28

### Added

- `--info` and version flags, and async support in the CLI.
- `renderMermaidToPage` API, unique diagram IDs and CSS injection.
- Module-level singleton and new helper functions.

### Changed

- Python requirement relaxed from 3.10+ to **3.9+**.
- Updated the phasma dependency (0.5.0, then 0.7.1) and reduced the project to a minimal version.
- Tests and CI: parallel test execution and shared converter fixtures.

### Fixed

- Escaped backslashes in docstring examples, and `read_text` encoding.

## [0.4.1] - 2026-01-21

### Fixed

- `__main__.py` is installed as an executable script.

## [0.4.0] - 2026-01-07

### Added

- PNG and PDF export with richer configuration options.
- Documentation site (Docusaurus) with an API reference.
- Logo and favicon.

### Changed

- Simplified `MermaidConverter` API: `Path` objects are accepted, width and height are optional,
  unused parameters and the Puppeteer config were removed, and output file path resolution improved.
- README now emphasizes the offline use case.

## [0.3.0] - 2025-12-28

### Added

- **PDF export.**
- PNG output with configurable dimensions and background.
- Mermaid source from stdin, CSS injection support and a `timeout` parameter.
- Automated version management and release workflow in CI.

### Changed

- Extracted the common rendering logic in `MermaidConverter` and cleared existing content before
  injecting the SVG.

## [0.2.0] - 2025-12-26

### Added

- Output format support and better error handling.

### Changed

- PNG and PDF conversion were temporarily disabled after `cairosvg` was removed, and the failing
  integration tests were skipped; `cairosvg` was added back as a core dependency.

## [0.1.0] - 2025-12-26

First release, under the name `mmdc`.

### Added

- Mermaid diagram converter built on PhantomJS (through `phasma`), with the Mermaid library bundled.
- CLI entry point with verbose logging.
- Integration tests, cross-platform CI, and a GitHub Actions workflow to build and release wheels.

[0.10.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.5...v0.10.0
[0.9.5]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.8.3...v0.9.0
[0.8.3]: https://github.com/mohammadraziei/mermaidx/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/mohammadraziei/mermaidx/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/mohammadraziei/mermaidx/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mohammadraziei/mermaidx/releases/tag/v0.1.0
