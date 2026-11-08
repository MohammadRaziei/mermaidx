# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/) (while below 1.0, a minor bump may carry breaking changes).

## [Unreleased]

### Fixed
- **A label made of `&nbsp;` was sized 0x0** (#23). The DOM shim decided whether a label has content with the JS
  regex `\S`, and JS counts U+00A0 as whitespace. mermaid's block arrow, `blockArrowId<["&nbsp;&nbsp;&nbsp;"]>(down)`,
  has such a label, so it came out at the minimum size and was smaller than in `mmdc`. Only HTML whitespace (space,
  tab, CR, LF, FF) counts as empty now, as in a browser.

## [0.11.2] - 2026-11-07

### Added

- **`mermaidx.Renderer`: workers with a lifetime you can see.** `with mermaidx.Renderer(workers=4) as renderer:` starts
  the workers, each with the engine its diagrams render in already loaded (so a bad option or a missing engine raises
  from the constructor, before anything is left running), and `renderer.render_many(batch)` can then be called again
  and again without starting anything; `close()` or the end of the block stops them. Nothing is kept by the module:
  no global pool, nothing at interpreter exit for a Renderer that was closed (one that was not is closed by a
  finalizer). Also `render(source)`, and `executor="thread"` or `"process"`. This replaces the idea of a pool that
  `render_many()` keeps between calls, which was tried first and dropped: its lifetime was implicit, and the Windows
  CI run of that version passed every test and then failed while shutting down (the cause was not established).

### Changed

- **`render_many()` uses threads by default**, and takes `executor="process"` for the old behavior. The old
  reasoning, that threads cannot overlap rendering because of the GIL, does not hold: the QuickJS binding gives the
  GIL back while JavaScript runs (a Python thread kept 51% of its speed on one core while another thread ran
  JavaScript), and the V8 engine runs in a child process of its own. Each worker thread has an engine of its own, so
  they do not take turns. They start faster than processes, use less memory, and no `Diagram` is pickled on its way
  back. `render_many()` also never starts more workers than there are sources. It still starts its workers for the
  call and stops them before it returns; for several batches use `Renderer`. Not measured: how much faster threads
  are than processes on a machine with several cores (the benchmark has `--scaling-executor` for that).
- **`third_party_licenses/` is now `licenses/`**, in the repository and in the wheel (`mermaidx/licenses/`, where it
  was `mermaidx/third_party_licenses/`). The license of the `quickjs-ng` package, from which
  `tools/quickjs_ng_bytecode/module.c` comes, is in it too.
- **`js:mermaid` renders about 2.8 times faster on QuickJS, from bytecode.** Every render gets a context of its own,
  and building one was almost all parsing: QuickJS compiles every function of a script when it loads it, so the 5.5 MB
  of `mermaid.js` took 600 to 800 ms to evaluate. The same script loaded as precompiled bytecode takes about 100 ms.
  The bytecode is made by the first context that needs it and kept in memory and in the cache directory of the user
  (`~/.cache/mermaidx/bytecode`, `MERMAIDX_CACHE_DIR` moves it, `MERMAIDX_BYTECODE_CACHE=0` turns it off), so a command
  line call for one diagram starts with it too: the first `start()` of a process went from 670-1200 ms to about
  200 ms. A cache file is only run if its checksum, the bytecode version of the QuickJS that reads it and the checksum
  of the script it was made from all match, and what is drawn is the same as from source (`tests/test_bytecode.py`
  compares them, ELK and ZenUML included). The ELK layout and ZenUML scripts, which are loaded for the diagrams that
  need them, go the same way. Measured from text to PNG over the 43 samples of `tests/samples`, one diagram after
  another: median 948 ms before, 340 ms after (p90 1572 ms before, about 900 ms after).
  **It needs `Context.compile()` and `Context.eval_bytecode()`, which the `quickjs-ng` package does not have yet:**
  `tools/quickjs_ng_bytecode/` builds `quickjs-ng` 0.18.0.1 with them (see its README). Without them nothing
  changes: the source is evaluated, as before.
- **`js:pele` renders about six times faster.** Every render used to get a context of its own, and building one
  (parsing the 730 KB of `pele.js`) took about 100 ms, against 1 ms for the render itself. pele keeps nothing between
  renders (all 43 samples of `tests/samples` give byte-for-byte the same SVG in one context as in a fresh one each,
  which `tests/test_engine_common.py` now checks, on both engines), so its contexts are reused, and replaced after
  1000 renders or after a render that failed. Measured from text to PNG, one diagram after another: median 128 ms
  before, 21.5 ms after. `js:mermaid` cannot do this: mermaid.js keeps id counters (`actor1`, `classId-Animal-0`, ...)
  and a random sequence between renders, so it still gets a fresh context for each diagram.

### Fixed

- **Starting several engines at once could leave the process's thread stack size at 32 MB.** `Engine.start()` sets
  `threading.stack_size()`, which is process-wide, around the start of its thread and puts it back; two engines
  started from two threads at once could put it back in the wrong order (12 of 12 runs with six workers). It is now
  done under a lock. Nothing started engines concurrently before `Renderer`.

### Tests, CI and docs

- **Architecture decision records in `docs/adr/`**: why every `js:mermaid` render gets a fresh context, why `mermaid.js` is
  loaded from cached QuickJS bytecode, how the two `quickjs-ng` methods it needs are meant to reach users, why CI and
  the benchmarks run the patched build, and what is known about the V8 backend's load time (still open).
- **CI runs the bytecode path.** The test job of `wheel.yml` builds the `quickjs-ng` wheel with `Context.compile()` and
  `Context.eval_bytecode()` (`tools/quickjs_ng_bytecode/build.sh`) and installs it over the one from PyPI, which does
  not have them, and sets `MERMAIDX_REQUIRE_BYTECODE=1`: with that variable `tests/test_bytecode.py` fails when the
  methods are missing instead of skipping its tests. Before, every run of CI used the stock package and skipped them.
- **The published benchmarks are measured with the bytecode build.** `docs/Makefile` installs the same patched wheel in
  its virtualenv, so `make all` (what CI runs) shows what `js:mermaid | quickjs` does with bytecode;
  `make all WITH_BYTECODE=0` keeps the stock package. The benchmark method page says which build was used.

## [0.11.1] - 2026-11-06

### Added

- **The ELK layout** (#33). `flowchart-elk`, `layout: elk` (in the frontmatter or in `config=`) and the other ELK
  algorithms (`elk.stress`, `elk.force`, `elk.mrtree`, ...) fell back to dagre without a word, because mermaid.js
  only knows ELK once `registerLayoutLoaders` has been called. `mermaidx/assets/layout_elk.js`
  (`@mermaid-js/layout-elk` 1.0.1 with elkjs, 2.4 MB, about 690 KB compressed in the wheel) is now evaluated for a
  diagram that asks for ELK, and only for that one, so no other diagram gets slower. It works on both engines.
  The diagrams that ask for ELK are laid out differently than before (they were drawn by dagre).
  `js:pele` has its own layout and ignores the request. Rebuild the file with `tools/build_layout_elk.sh`.
- **ZenUML diagrams** (#20) render now, on both engines. ZenUML is not part of Mermaid's core: its plugin
  (`@mermaid-js/mermaid-zenuml`) draws HTML with React into a `foreignObject` and asks a browser how big it came out,
  which the DOM shim cannot do. mermaidx uses another way: the command line tool of `@zenuml/core` has a renderer of
  its own, `renderToSvg()`, that writes plain SVG (no `foreignObject`, so every rasterizer can paint it).
  `mermaidx/assets/zenuml.js` (`@zenuml/core` 3.50.1, 406 KB, about 104 KB compressed) is evaluated for a diagram
  that starts with `zenuml`, and only for that one. It measures text with the canvas of the DOM shim, so it gets the
  same real font metrics as mermaid.js. The theme and the config of mermaid do not apply to it, and `js:pele` does not
  know ZenUML. Rebuild the file with `tools/build_zenuml.sh`.
- **Five more charts on the benchmark page**, under "More measurements": the size on disk of every renderer (mmdc
  with its Chromium against mermaidx with its engine), the share of the words of the mermaid-cli reference that each
  renderer drew, the first render against the ones after it, how `render_many()` speeds up with more worker
  processes, and the time of every diagram, ordered by the length of its Mermaid text. `benchmarks/run.py` writes the new
  data into `results.json` (`footprint`, `scaling`, and `chars` and `labels` for the samples), and has the new options
  `--scaling-items` and `--scaling-repeats`. The page still works with a `results.json` made by an older script. How
  each one is measured is in "How the benchmarks work".
- **ELK layout and ZenUML in the benchmark.** Seven new diagrams in `benchmarks/samples` (three `layout: elk` flowcharts,
  three ZenUML sequence diagrams and the bare `info` diagram) are rendered by every renderer, `benchmarks/run.py` reads that directory next to
  `tests/samples` (`--samples` can be given more than once), and `results.json` marks each sample with `feature`
  (`elk`, `zenuml` or `null`) and `reference` (whether it has a mermaid-cli `.svg`). They are not in `tests/samples`
  because the tests there need a reference for every sample. The median time, the speed-up and the parallel measurement
  use the core diagrams only.
- **ELK and ZenUML in the gallery.** These diagrams have a badge, the filters "ELK layout only" and "ZenUML only", and
  a renderer that cannot draw one shows "Not supported" with its error. `js:pele`, which has no ELK layout and draws
  those flowcharts with its own, is marked as such under the diagram.

- **`NOTICES.md` and `third_party_licenses/`**: the licenses of the JavaScript files in `mermaidx/assets`
  (mermaid.js, pele, @zenuml/core with antlr4 and marked, the ELK layout with elkjs, which is EPL-2.0) next to the
  DejaVu license that was already there. They are also in the wheel, under `mermaidx/`.
- **`-f`/`--format` for the command line** (#46). The format of the output came only from the extension of `-o`, so
  standard output could only ever be SVG. `mermaidx -i flow.mmd -f png > flow.png` (or `-o -`) now writes any format to
  standard output: `svg`, `png`, `jpg`, `jpeg`, `bmp`, `tga` or `pdf`, with the size, background, `--quality` and PDF
  options applying as they do for a file. `-f` also overrides the extension of a file, and names the format of a file
  without one (`-o diagram -f pdf`). Without `-f` nothing changes: the extension of `-o` decides, and standard output
  is SVG. Binary formats are raw bytes, so a pipe or a redirect gets a valid file; a terminal gets an error instead of
  garbage. **`--data-uri`** writes `data:image/png;base64,...` instead, for HTML, Markdown or JSON.

### Changed

- `novasvg` is now pinned to exactly 0.11.5 (`==`, not a minimum). mermaid.js 12.3 colors the nodes of some diagrams (the entities of an ER
  diagram, for one) with CSS rules that select on attributes (`[data-look="neo"][data-color-id="color-0"].node path`),
  which novasvg before 0.11.5 does not apply: the SVG was colored, but the PNG, JPEG and PDF made from it came out
  without those colors. 0.11.5 applies them.
- **mermaid.js 12.2.0 -> 12.3.0** (the minified `dist/mermaid.min.js`, unmodified). It bundles DOMPurify 3.4.17 instead
  of 3.4.12, which needed one more thing from the DOM shim (see "Fixed").
- **pele 1.12.0 -> 1.13.0** (the minified `dist/pele.js` from npm, `mermaidx/assets/pele.js`).

### Removed

- **ASCII output.** `mermaidx.render_ascii()`, `Diagram.ascii()` and the `ascii` format of `save()` (the `.txt` and
  `.ascii` extensions) are gone, together with the `termaid` dependency: it had nothing to do with what mermaidx is
  for, rendering Mermaid to SVG and the formats made from it. Code that used them has to drop them, or draw the
  diagram with `termaid` itself.

### Fixed

- An output file with an extension mermaidx does not know (`-o diagram.xyz`) ended in a Python traceback. It is a usage
  error now, and the message points at `-f`.
- **DOMPurify removed nothing with mermaid.js 12.3.** The DOMPurify inside it (3.4.17; mermaid.js 12.2.0 had 3.4.12)
  removes an attribute with `Element.prototype.removeAttributeNode`, which the DOM shim did not have. DOMPurify looks
  it up in a way that makes a missing method a silent no-op, so every attribute it decided to drop stayed in the SVG:
  `onclick` on a label, and mermaid's own layout scratch attributes (`label-offset-y`, `text-height`, `position`). The
  shim now has `getAttributeNode()` and `removeAttributeNode()`, and `tests/test_sanitization.py` covers it.
- **The text of a PNG is painted in the font the layout was measured with.** The SVG names mermaid.js's own font stack
  (`"trebuchet ms", verdana, arial` or `"Recursive Variable", arial`), and novasvg took the first of those names the
  host had (Arial, Liberation Sans...), a narrower font than the bundled DejaVu Sans that the layout is measured with.
  Labels then took fewer lines than their boxes were made for and the boxes looked too tall (`10_flowchart_long_label`).
  Those names are now pointed at the bundled DejaVu Sans, so the pixels agree with the layout on every host. The SVG
  was never affected.
- **quickjs-ng 0.18.** It hands a long string (a rope) to Python itself, where older bindings raised `Unknown quickjs
  tag`. The `__flat` wrappers stay, because `quickjs-ng>=0.15.1` is still allowed and they are harmless on 0.18; two
  tests that required the old error now accept both behaviors.
- **US spelling** in the code, the messages and the docs (#42, #44): recognize, colors, Enroll, label-center.
- **The docs site favicon has a transparent background.** `docs/static/img/favicon.svg` had a light rectangle behind
  the logo, which showed as a white box in browser tabs.

## [0.11.0] - 2026-11-01

Two breaking changes to how a renderer is chosen, a new renderer (pele), and Mermaid 12.

### Changed (breaking)

- **Backends are named `<kind>:<name>`.** `backend="quickjs"` and `backend="v8"` are now
  `backend="js:mermaid"` (the default); `backend="merman"` and `backend="mermaid-rs-renderer"` are now
  `backend="rust:merman"` and `backend="rust:mermaid-rs-renderer"`. `mermaidx.backends()` returns the new
  names. A bare name raises `ValueError` that says which name replaces it; it is not silently accepted.
- **`quickjs` and `v8` are now values of a separate `engine` parameter** of `render()` and `Diagram`:
  `engine="quickjs"` or `engine="v8"`. It is `None` unless you set it. For a `js:` backend `None` means
  `"quickjs"`; a `rust:` backend has no JS engine and raises `ValueError` if you pass one. The CLI gets a
  matching `--engine` option. `render_many()` forwards both.
- `ImportError` for a missing `mini-racer` now names the right extra, `mermaidx[v8engine]`
  (it said `mermaidx[v8]`, which does not exist), and is raised for `engine="v8"`.
- The minimum `novasvg` is now 0.11.4 (see below).
- **The bundled mermaid.js is now v12.2.0** (the minified `dist/mermaid.min.js`; it was v11.16.0), the version
  `mmdc` 12 (mermaid-cli 12.0.0) uses. Mermaid 12 draws some diagrams differently from 11 (new `neo` look,
  other shapes and edge routing), so diagrams can look different after upgrading.
- **No theme is sent unless you ask for one.** `theme=None` (the default, also `--theme` on the command line) now
  leaves the choice to Mermaid, exactly as `mmdc` does, and Mermaid 12 gives each diagram type its own theme and
  look. Before, `theme="default"` was always sent. Pass `theme="default"` to get the uniform look of the old
  default. The CLI `--theme` now accepts every Mermaid 12 theme (`neo`, `neo-dark`, `redux`, `redux-dark`,
  `redux-color`, `redux-dark-color`, `base`, `null` as well).

### Added

- **`backend="js:pele"`**: [pele](https://pele.run) 1.13.0, a small synchronous Mermaid renderer written in
  JavaScript, bundled as `mermaidx/assets/pele.js` and runnable on either engine. It has its own layout, so
  its output differs from mermaid.js (all 43 diagrams in `tests/samples` render). It is themed with CSS variables instead of Mermaid
  themes: `theme` must be unset (or `"default"`), `config` is passed to pele, and `css` is added to the SVG
  as a `<style>` (for example `css="svg{--pele-bg:#111;--pele-fg:#eee}"`).
- `mermaidx.available_engines()`, the counterpart of `backends()` for `engine=`.
- The CLI reports a bad `--backend`, `--engine` or `--theme` combination as a usage error (exit code 2)
  instead of a traceback, and `--list-backends` also lists the engines.

### Fixed

- **Rendering a c4 diagram took minutes** (157 s for `24_c4_context`, a few seconds for other diagrams) because
  the DOM shim parsed every CSS selector again on each match and rebuilt the whole stylesheet text for each font
  lookup. Selector parses are cached, the stylesheet is read once per lookup, and what each element resolved to is
  remembered for the length of one `getBBox` / `getComputedTextLength` call. The c4 sample now takes about 7 s;
  of the others, `37_erd_relations` went from 4.2 s to 2.6 s and `38_class_advanced` from 4.2 s to 3.2 s, and a
  simple flowchart is unchanged (about 1.4 s). The output of the other 42 samples is byte-for-byte what it was
  (apart from random ids), and the c4 sample differs from `mmdc` in the same 44 places as before.
- The DOM shim now provides what Mermaid 12 asks of a browser: `CSSStyleSheet` rules with a live `style` object
  (`setProperty`, `length`), `SVGElement.ownerSVGElement`, `SVGGeometryElement.getTotalLength()` (it sizes the dashes
  of an edge; it was missing, so they came out as `0 0 -4 4`) and `nodeType` as a prototype accessor, which
  DOMPurify needs to recognize a node. Without the last one DOMPurify dropped a whole diagram whose label contained
  `<<...>>`, as the requirement diagram does.
- The SVG path walker behind `getBBox()` now also reads a `Z` at the very end of a path (it was only read when
  another character followed). The box does not change, but the new path length needs the closing segment.

### Tests, CI and docs

- The 43 reference SVGs in `tests/samples` are rendered again with mermaid-cli 12.0.0 (recipe in
  `tests/samples/README.md`). The structural test allows one pixel on numbers. `24_c4_context`,
  `37_erd_relations` and `38_class_advanced` are recorded as strict expected failures on both engines: Chrome
  rounds a fractional font size before measuring, which can move a wrap or a size threshold (see Known issues).
- The label-center check in `tests/test_samples.py` skips `24_c4_context`, whose label group is placed by its
  top-left corner in Mermaid 12 (`mmdc` does the same).
- pytest runs with `pytest-timeout` (120 s, `thread` method, which also works while a JS engine is running native
  code) and prints the 25 slowest tests (`--durations`). It is part of the `test` extra.
- The benchmark names its renderers `@mermaid-js/mermaid-cli`, `js:mermaid | quickjs`, `js:pele | v8`,
  `rust:merman` and so on.
- The `Makefile` for the docs and the benchmark moved from the repository root to `docs/`; run `make` from there.

### Migrating

| 0.10 | 0.11 |
| --- | --- |
| `render(src)` / `backend="quickjs"` | `render(src)` / `backend="js:mermaid"` |
| `backend="v8"` | `engine="v8"` |
| `backend="merman"` | `backend="rust:merman"` |
| `backend="mermaid-rs-renderer"` | `backend="rust:mermaid-rs-renderer"` |
| `mermaidx --backend v8` | `mermaidx --engine v8` |

### Fixed

- **`render_many()` did not render in parallel** (#43, reported by @almeidamaxwell). The workers only built
  the lazy `Diagram` objects and sent them back unrendered, so every SVG was then rendered one after another
  in the caller's process, at the speed of a plain loop. The workers now render the SVG before returning it,
  so the parse and layout work is spread over the processes. `.svg()` on the result returns at once; the
  other formats are still made from that SVG when first asked for. A diagram that fails to render comes
  back unrendered and raises on `.svg()`, as before. With `workers=1` the SVGs are likewise rendered
  before `render_many()` returns.
- pele paints with nested CSS variables (`var(--pele-bg, #fff)`), which novasvg before 0.11.4 does not
  resolve, so every shape came out solid black. 0.11.4 does.

## [0.10.1] - 2026-10-21

A patch release for a regression in 0.10.0: on the default `quickjs` backend, a diagram whose text held a
character above U+00FF failed to render.

### Fixed

- **`TypeError: Unknown quickjs tag: -6` on the `quickjs` backend** for any label, title or message holding
  a character above U+00FF (an em dash, a bullet, `≥`, a circled digit, Persian, CJK, an emoji) (#39, fix by
  @kamalkraj in #40). QuickJS-ng keeps a long concatenation as a rope string, which the `quickjs` Python
  binding cannot convert. Every string that crosses into Python (the rendered SVG, the error text and the
  arguments of the text-measurement callbacks) is now copied into a flat one first. A long label of that kind
  used to fail earlier, inside a measurement callback. The `v8` engine is unchanged.
- The link to the changelog on the installation page of the docs had the wrong letter case, which broke
  the docs build.

### Changed

- Spelling is now US-English throughout the code comments, the docs and the error messages (#42). The one
  visible effect: the error for an invalid background color now starts with `Unrecognized background color`.

### Added

- `tests/test_unicode_labels.py` covers #39 for ten diagram types, for SVG, PNG and PDF output, for the
  error path and for the flattening helper itself. The `v8` cases are skipped when `mini-racer` is not
  installed.

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

[0.11.2]: https://github.com/mohammadraziei/mermaidx/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/mohammadraziei/mermaidx/compare/v0.10.1...v0.11.0
[0.10.1]: https://github.com/mohammadraziei/mermaidx/compare/v0.10.0...v0.10.1
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
