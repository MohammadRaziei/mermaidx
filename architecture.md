# mermaidx architecture

This document explains how `mermaidx` turns a `.mmd` source string into SVG/PNG/PDF/ASCII **without a browser** — the core trick, the two files that do almost all of the work (`engine.py` and `assets/dom_shim.js`), and the algorithm behind the single hardest part: making a fake DOM answer layout questions (`getBBox()`, `getBoundingClientRect()`, `getContext("2d").measureText()`) correctly enough that mermaid.js's own layout engine (dagre / cytoscape) produces the same result it would in a real browser.

Diagrams in this file are plain Mermaid, rendered by GitHub natively — and, of course, by `mermaidx` itself.

---

## 1. The core idea

mermaid.js is a real, unmodified npm package — not a reimplementation, not a subset. It's JavaScript, and it expects to run in a browser: it wants `document.createElementNS`, `getBBox()`, a `<canvas>` it can call `getContext("2d")` on, `requestAnimationFrame`, and so on.

`mermaidx` gives it all of that — except there's no browser underneath. There's a small, embeddable JS engine (**QuickJS-ng**) running a **hand-written fake DOM** (`dom_shim.js`, ~765 lines). mermaid.js can't tell the difference, as long as the fake DOM answers its questions the way a real one would.

```mermaid
flowchart LR
    subgraph py["Python process"]
        API["mermaidx.render()"] --> ENG["Engine\n(engine.py)"]
        ENG -- "measureText / getBBox\npathBBox callbacks" --> FM["font_metrics.py\n(novasvg.fonts: glyph widths,\nkerning, foreignObject sizes)"]
        ENG --> RAST["raster.py\n(novasvg)"]
        RAST --> OUT["PNG / PDF / numpy"]
    end
    subgraph qjs["QuickJS-ng context (one dedicated thread)"]
        SHIM["dom_shim.js\nfake DOM / CSSOM / Canvas2D"]
        MMD["mermaid.js v12\n(unmodified, ~5.5MB)"]
        SHIM -.->|"mermaid.js runs\nagainst the shim"| MMD
    end
    ENG <-->|"eval() / add_callable()"| qjs
    MMD -->|"SVG string"| ENG
    style py fill:#eef,stroke:#88a
    style qjs fill:#efe,stroke:#8a8
```

**Why this instead of Puppeteer/Chrome (what the official `mermaid-cli` does):** no browser to install or boot means far less startup cost per render, no Chromium download, and no OS-specific browser-automation flakiness. The trade-off is that a fake DOM has to *actually be correct* — every gap between it and a real browser's behavior becomes a rendering bug. Most of the interesting engineering in this project is closing those gaps, described below.

---

## 2. End-to-end sequence: one `render()` call

```mermaid
sequenceDiagram
    autonumber
    participant U as User code
    participant D as Diagram (diagram.py)
    participant E as Engine (engine.py)
    participant Q as QuickJS context
    participant S as dom_shim.js
    participant M as mermaid.js
    participant R as novasvg (raster.py)

    U->>D: mermaidx.render(".mmd source")
    D->>E: render_svg(code, theme, config, css)
    Note over E: runs on Engine's one<br/>dedicated worker thread
    E->>Q: __resetDocument()
    E->>Q: mermaid.initialize(config)
    E->>Q: mermaid.render(id, code)  [async, returns a Promise]
    activate Q
    Q->>M: parse .mmd, build layout graph
    loop for every label / shape (100-300+ times per diagram)
        M->>S: text.getBBox() / div.getBoundingClientRect()
        S->>E: __measureTextFull_raw(text, size, family, weight)<br/>or __measureForeignObject_raw(html, size, ...)
        E->>E: font_metrics.py asks novasvg (same DejaVu Sans<br/>file novasvg paints with#59; kerning-aware)
        E-->>S: {width, ascent, descent}
        S-->>M: DOMRect-shaped result
        M->>S: shape.getBBox()  (after drawing a <path>/<polygon>)
        S->>E: __pathBBox_raw(d)  [only for <path>]
        E-->>S: bbox (real SVG-arc-aware parser, see §4)
        S-->>M: DOMRect-shaped result
    end
    M-->>Q: Promise resolves with {svg: "..."}
    deactivate Q
    E->>Q: _pump_jobs(stop_when="renderResult set")
    Note over E,Q: drains the microtask queue, but stops the<br/>moment the result is ready -- some diagrams<br/>(mindmap, via cytoscape) keep an internal<br/>rAF loop scheduled forever otherwise
    Q-->>E: SVG string
    E->>E: apply small, targeted post-render<br/>CSS patches (documented gaps in<br/>mermaid.js's own generated stylesheet)
    E-->>D: SVG string
    D->>R: render_png(svg)  [only if .png()/.pdf() is called]
    R-->>D: PNG bytes (or PDF, or a numpy array)
    D-->>U: Diagram object (svg/png/pdf/numpy, lazily cached)
```

Two things worth noticing:

- **The callback bridge (steps 6-13) is the hot path.** A single moderately complex diagram makes 100-300+ round trips from JS into Python and back, each one answering "how big is this text/shape". This is also *why* a from-scratch C++ rewrite (discussed in `architecture-notes`/project history) targets this bridge specifically rather than the JS engine choice — profiling showed ~98% of render time is this loop, not the final rasterization step.
- **The Promise chain has to be pumped manually** (`_pump_jobs`). QuickJS has no event loop of its own; `execute_pending_job()` runs one microtask at a time, and `Engine` calls it in a loop until the result is ready. Early on this loop had no early-exit condition and would drain a diagram type's entire internal animation-frame queue (hundreds of thousands of no-op iterations) even after the real answer was ready — see §6.

---

## 3. The DOM/CSSOM shim: class shape

`dom_shim.js` is a single file implementing just enough of the DOM, CSSOM, and Canvas 2D APIs for mermaid.js to run unmodified. It is **not** a general-purpose DOM implementation — every method exists because something in mermaid.js's actual bundle calls it.

```mermaid
classDiagram
    class Node {
        +nodeType
        +childNodes[]
        +parentNode
        +appendChild(c)
        +insertBefore(c, ref)
        +removeChild(c)
        +getRootNode()
        +ownerDocument
    }
    class Element {
        +tagName
        +attributes
        +style : CSSStyleDecl
        +classList : ClassList
        +getAttribute(k)
        +setAttribute(k, v)
        +getBBox()
        +getBoundingClientRect()
        +getContext("2d")
        +getElementsByTagName(tag)
        +querySelector(sel) / querySelectorAll(sel)
        +innerHTML get/set
    }
    class TextNode {
        +textContent
    }
    class Document {
        +createElement(tag)
        +createElementNS(ns, tag)
        +createTextNode(t)
        +getElementById(id)
        +addEventListener(t, fn)
    }
    class CSSStyleDecl {
        +getPropertyValue(k)
        +setProperty(k, v)
        <<Proxy-backed>>
    }
    class ClassList {
        +contains(c) / add(c) / remove(c)
    }
    Node <|-- Element
    Node <|-- TextNode
    Node <|-- Document
    Element o-- CSSStyleDecl
    Element o-- ClassList
    note for Element "getContext for 2d only returns something<br/>real when tagName is canvas"
```

Everything mermaid.js actually touches funnels through a handful of module-level functions rather than being spread across the classes above:

| Function | Role |
|---|---|
| `__computeBBox(el)` | The single most important function in the file — see §4. |
| `__resolveFont(el)` / `__resolveTextAnchor(el)` / `__resolveTextPos(el, fontSize)` | Walk up the ancestor chain (and, for text-anchor, into the parsed `<style>` block) to resolve *computed* font/anchor/position — a real DOM never asks the element itself, it asks "what does CSS say applies here". |
| `__getCssRules()` / `__resolveCssProp(el, prop)` | A tiny CSS parser + the same selector engine used for `querySelector`, reused to answer "what would `getComputedStyle` say" for the handful of properties mermaid's *layout* code actually reads (as opposed to properties that only affect paint, which novasvg handles natively). |
| `__matches(el, sel)` / `__matchesCompound(el, part)` | A CSS selector engine covering descendant combinators, `.class`, `#id`, `[attr]`, and the pseudo-classes mermaid/d3 actually use (`:first-child`, `:last-child`, `:not(...)`) — enough for `d3.select(...).insert(tag, ":first-child")`, a pattern mermaid's shape-drawing code relies on constantly. |
| `__makeCanvas2dContext(canvasEl)` | A Canvas 2D stub: every drawing method (`fillRect`, `arc`, `bezierCurveTo`, ...) is a no-op, since mindmap's cytoscape-based layout never has its pixels read back — only `measureText()` is real, because layout math depends on it. |
| `__parseInto(parent, html)` / `__serialize(el, innerOnly)` | innerHTML get/set, used for mermaid's HTML-label code paths. |

---

## 4. The algorithm mermaid actually depends on: `getBBox()`

Every layout decision mermaid.js makes — how wide a node needs to be, where to center a label, how far apart to space two nodes — ultimately traces back to a `getBBox()` (or `getBoundingClientRect()`) call somewhere. Get this wrong and the *symptom* is never "getBBox is wrong" — it's "text is clipped", "two nodes overlap", or "a label sits outside its own shape". This is the function almost every bug fix in this project's history came back to.

```mermaid
flowchart TD
    START(["el.getBBox()"]) --> TAG{"el.tagName?"}

    TAG -- "text / tspan" --> POS["__resolveTextPos(el, fontSize)\nwalk into the ONE positioning\ntspan mermaid actually writes,\nhonoring y / dy in *em* units"]
    POS --> MEAS["__measureTextFull(text, font)\n→ Python → font_metrics.py\n(real DejaVu Sans glyph widths + kerning,\nsame file novasvg paints with)"]
    MEAS --> ANCHOR["__resolveTextAnchor(el)\ninline style → external &lt;style&gt;\nrules → attribute → default 'start'"]
    ANCHOR --> TEXTOUT(["{x, y, width, height}\nadjusted for start/middle/end"])

    TAG -- "rect" --> RECTOUT(["read x/y/width/height\ndirectly off attributes"])

    TAG -- "polygon / polyline" --> POLY["parse the points attribute:\nmin/max over every x,y pair"]
    POLY --> POLYOUT(["bbox"])

    TAG -- "circle / ellipse" --> ELL["cx,cy,rx,ry → bbox"]
    ELL --> ELLOUT(["bbox"])

    TAG -- "path" --> PBBOX["__pathBBox(d) → Python\n_path_bbox(): a real SVG path\ncommand parser (M/L/H/V/C/S/Q/T/A/Z),\nnot a naive number-pair split"]
    PBBOX --> ARC{"contains an\nA (arc) command?"}
    ARC -- yes --> EXTREMA["_arc_extrema(): SVG 1.1 Appendix F.6\nendpoint-to-center parameterization,\ntrue extrema, not padded guesses"]
    ARC -- no --> SIMPLE["M/L/C/... endpoints\n+ control points\n(deliberately generous)"]
    EXTREMA --> PATHOUT(["bbox"])
    SIMPLE --> PATHOUT

    TAG -- "g / unknown" --> UNION["union of every child's bbox,\neach mapped through that child's\nown translate(x,y) transform\nbefore combining"]
    UNION --> UNIONOUT(["bbox"])

    TEXTOUT --> DONE(["returned to mermaid.js,\nfeeds directly into dagre /\ncytoscape layout math"])
    RECTOUT --> DONE
    POLYOUT --> DONE
    ELLOUT --> DONE
    PATHOUT --> DONE
    UNIONOUT --> DONE
```

Three of these branches are worth calling out because each one was, at some point, simply **absent** (silently falling through to the group-union branch and returning a zero-size box), and each absence produced a different, non-obvious visual symptom:

- **No `polygon` case** → `updateNodeBounds()` (mermaid's own function that reports a shape's final size back to its layout graph) always got `{width: 0, height: 0}` for any polygon-based shape (subroutine boxes, diamonds). The layout engine then placed every other node as if that shape took up no space at all — nodes overlapping, text stacked on text.
- **Naive `path` bbox** (flat number list split into alternating x/y pairs) → correct for `M`/`L`/`C` only. An `A` (arc) command has 7 numbers (`rx,ry,rotation,large-arc,sweep,x,y`), not 2 — desyncing the split for the rest of the path. Cylinder and stadium shapes (which use arcs for their rounded caps) got corrupted bounding boxes, clipping them off the edge of the final diagram.
- **Group bbox ignoring child transforms** → `getBBox()` on a `<g>` unioned its children's boxes *without* applying each child's own `transform="translate(x,y)"` first. Since mermaid positions essentially every node via exactly that attribute, the computed size of the whole diagram was close to the size of a single node at the origin — clipping almost everything else.

None of these are exotic: they're all direct consequences of the same principle — **a fake DOM's `getBBox()` has to implement the actual SVG geometry spec for each element type, not "the subset of cases the sample diagrams happened to exercise."**

---

### Speed: what the style cascade costs

Finding the font of a text means walking up its ancestors and matching every rule of the diagram's `<style>` against each one, and a group's `getBBox()` does that for every text below it. Mermaid 12 writes a much larger stylesheet than 11 did, and the c4 sample took 157 s before this was cached. Three things keep it fast, none of which change a result: a selector's parse is kept (`__chainsOf`, `__parseCompound`), the stylesheet is read once per font lookup, and the CSS and font each element resolved to are remembered only while one `getBBox` / `getComputedTextLength` call runs (`__withCssMemo`), so a later call after the document changed starts from scratch. The same sample now renders in about 7 s.

## 5. Text sanitization (`sanitizeText` / DOMPurify) works; labels with `<img>` do not

mermaid.js runs essentially all label text through an internal `sanitizeText()` helper before it reaches layout or drawing. That helper is a thin wrapper around a bundled copy of **DOMPurify** (the real, unmodified npm package: the same one that strips unsafe HTML out of user-supplied labels in a real browser). DOMPurify does no work at all unless it finds a "real enough" browser DOM, so `dom_shim.js` provides what its support probe and its parser need, and the real sanitizing then runs:

- `Node.prototype` accessors for `parentNode`, `childNodes` and `nodeType`. DOMPurify looks them up with `Object.getOwnPropertyDescriptor` on the prototype chain, and an own instance property does not satisfy that. Without the `nodeType` accessor its "is this a Node" test fails for every node, and its check for markup smuggled into text then removes the whole `<svg>`, which is what happened to a requirement diagram whose label contained `<<Requirement>>`.
- `document.implementation.createHTMLDocument()` and `createDocument()`, `DOMParser`, `NodeFilter` and `NodeIterator`.

Entity decoding and tag stripping now behave as in a browser. They were compared with `mmdc` 12 on the same labels: `&copy;`, `&#160;` and `&nbsp;` come out as `mmdc` has them, `<b>` and `<i>` are kept, `<script>` is removed, and an `onclick` attribute is removed. (An earlier version of this document described DOMPurify as a no-op, with `&nbsp;` decoded by hand when a text node was built. The decoding in `dom_shim.js` is still there; the sanitizer no longer depends on it.)

**What does not work: a label with an `<img>`.** `mermaid.render()` fails with `produced no output (unknown error)`, where `mmdc` keeps the image. After building such a label mermaid waits until `img.complete` is true or the image fires `load` or `error`, and this shim has neither: an image is never loaded, so the render promise never settles. The likely fix is to give `img` a `complete` of `true`, or to fire `error` once, in the shim; that has not been tried. Nothing in the test suite renders an image label.

---

## 6. Async without a browser: the job-pump model

QuickJS has no event loop, no timers, and no real 60fps frame clock. `requestAnimationFrame` and `setTimeout` are polyfilled (`dom_shim.js`, bottom), and `Engine._pump_jobs()` (`engine.py`) manually drains QuickJS's own Promise/microtask queue after kicking off `mermaid.render()`.

```mermaid
flowchart LR
    A["mermaid.render(id, code)\nreturns a Promise"] --> B["_pump_jobs(stop_when)"]
    B --> C{"stop_when true?\n(renderResult or\nrenderError is set)"}
    C -- yes --> DONE(["return SVG string"])
    C -- no --> D{"execute_pending_job()\nany job left?"}
    D -- no --> DONE
    D -- yes --> E["run one microtask\n(could itself schedule\nmore jobs, e.g. via\nrequestAnimationFrame)"]
    E --> C
```

Two real bugs lived here:

1. **Synchronous rAF/setTimeout.** The first version ran the callback immediately, inline. In a real browser, a redraw handler that itself schedules another `requestAnimationFrame` unrolls across separate frames — the call stack unwinds in between. Run synchronously, that same pattern recurses directly: cytoscape's render loop (used by the mindmap diagram type) does exactly this, and it blew the JS call stack (`RangeError: Maximum call stack size exceeded`). Fix: defer both through `Promise.resolve().then(...)`, so each call becomes a fresh job on the microtask queue instead of a nested call.
2. **No early exit.** Even after (1), `_pump_jobs` drained the *entire* queue before returning. cytoscape's renderer keeps an animation loop scheduled indefinitely (correct behavior for a page that stays open — meaningless for a one-shot headless render). The actual SVG result was ready after ~150 jobs; the loop kept running until its 200,000-job safety cap, ~100x longer than necessary. Fix: `stop_when` — poll a JS boolean expression each iteration and return the moment it's true.

---

## 7. Where the layers hand off

```mermaid
flowchart TD
    MMD[".mmd source string"] --> ENGINE
    subgraph ENGINE["Engine (engine.py)"]
        direction TB
        E1["QuickJS context\n+ dom_shim.js + mermaid.js"]
        E2["_TextMeasurer\n→ font_metrics.py"]
        E3["_path_bbox / _arc_extrema"]
        E1 <-.-> E2
        E1 <-.-> E3
    end
    ENGINE --> SVGSTR["raw SVG string\n(+ small targeted CSS patches\nfor documented mermaid.js gaps,\ne.g. mindmap label centering)"]
    SVGSTR --> DIAG["Diagram / DiagramBase\n(diagram.py) -- lazy, cached"]
    DIAG -->|".svg()"| SVGOUT["SVG string"]
    DIAG -->|".png() / .pdf() / .numpy()"| RASTER["raster.py → novasvg\n(same DejaVu Sans font file\nas font_metrics.py, so layout\nand paint agree by construction)"]
    DIAG -->|".ascii()"| ASCII["ascii.py → termaid"]
    RASTER --> PNGOUT["PNG bytes"]
    RASTER --> PDFOUT["pdf_writer.py\n→ PDF bytes"]
    RASTER --> NPOUT["numpy array"]
```

`backends.py` sits alongside this as a pluggable second path: if the optional `mmdr` (native-Rust) package is installed, its backends (`merman`, `mermaid-rs-renderer`) are picked up automatically, each producing its own `.svg()`  — everything downstream of that (`.png()`, `.pdf()`, `.numpy()`) still goes through *this* project's `raster.py`/`pdf_writer.py`, since `DiagramBase` implements those once, shared by every backend.

---

## 8. File reference

| File | Responsibility |
|---|---|
| `mermaidx/engine.py` | Owns the QuickJS context (one per process, one dedicated thread). Wires up the Python↔JS callback bridge (`__measureText`, `__measureTextFull`, `__pathBBox`). Implements `_path_bbox`/`_arc_extrema` (real SVG path geometry). Drives the job-pump loop. Applies the small set of documented post-render CSS patches. |
| `mermaidx/assets/dom_shim.js` | The fake DOM/CSSOM/Canvas2D. `Node`/`Element`/`Document`/`TextNode`/`CSSStyleDecl`/`ClassList`. The `getBBox()` dispatch (§4). The CSS selector engine (`__matches`/`__matchesCompound`). The Canvas 2D stub. Timer/event polyfills. |
| `mermaidx/assets/mermaid.js` | mermaid.js v12 (12.2.0, `dist/mermaid.min.js`), unmodified, bundled via esbuild. Never patched directly — every gap is compensated for in the shim or engine.py instead, so upgrading this file doesn't mean re-auditing hand-edits. |
| `mermaidx/assets/layout_elk.js` | The ELK layout (`@mermaid-js/layout-elk` with elkjs), bundled by esbuild into one script that calls `mermaid.registerLayoutLoaders`. 2.4 MB, so it is not in the context every render starts from: `render_script()` puts it in front of the render of a diagram for which `needs_elk()` is true. Rebuild with `tools/build_layout_elk.sh`. |
| `mermaidx/assets/zenuml.js` | The SVG renderer of ZenUML: `renderToSvg()` cut out of the command line tool of `@zenuml/core` (the plugin `@mermaid-js/mermaid-zenuml` needs a browser to measure HTML) and bundled by esbuild into `globalThis.__zenuml`. 406 KB, so it is only part of the render script of a diagram for which `zenuml_body()` finds a `zenuml` header: `render_script()` then skips mermaid.js and calls `zenuml_render_script()`. It measures text with the canvas of the DOM shim. Rebuild with `tools/build_zenuml.sh`, which stops if the file of `@zenuml/core` no longer has the expected shape. |
| `mermaidx/font_metrics.py` | Thin wrapper over `novasvg.fonts` (vendored stb_truetype): real glyph advances, kerning, and `<foreignObject>` label sizes for the bundled DejaVu Sans. The *only* source of text-measurement truth, shared by the shim's `getBBox()`/`getBoundingClientRect()` and — since it's the same engine — novasvg's final paint. For V8 (no synchronous callbacks) it also exports the advance table and a sparse ASCII kerning table for a JS-side mirror. |
| `mermaidx/raster.py` | SVG → PNG via novasvg, using that same font file. |
| `mermaidx/pdf_writer.py` | PNG → PDF, hand-written (not novasvg). |
| `mermaidx/diagram.py` | `DiagramBase`/`Diagram`/`DiagramRust` — the lazy, cached public object `render()` returns. |
| `mermaidx/backends.py` | Discovers optional `mmdr`-provided backends. |
| `mermaidx/ascii.py` | SVG → ASCII/Unicode art via `termaid`. |
| `tests/test_samples.py` | Structural checks (label text, aspect ratio) *and* geometry/pixel checks (content not clipped, shapes painted before labels, labels not stacked on siblings, label ink pixel-centered in its shape) — the geometry/pixel checks exist specifically because the structural ones are provably blind to whole classes of real rendering bugs. |

---


### `<foreignObject>` label sizing (htmlLabels)

Two spots in `dom_shim.js` exist specifically so HTML labels size correctly with no real CSS engine underneath:

- **`getBoundingClientRect()`** serializes the element's `innerHTML` and asks `__measureForeignObject` for `{width, height, line_count, line_height}`. QuickJS answers via a synchronous callback into `novasvg.fonts.measure_foreign_object()` (the exact line-counting / `line-height` logic novasvg's painter uses). V8 can't call back synchronously, so `v8_engine.py` ships a line-for-line JS mirror of that algorithm instead — the same pattern as its advance/kerning tables. Multi-line (`<br>`) labels grow their boxes correctly because of this.
- **`__computeBBox()`** has an explicit `foreignObject` case returning its own `width`/`height` attributes. Without it, the generic "union of children" fallback asks HTML children for an SVG bbox they don't have, under-reports the diagram's extent, and mermaid sizes the final `viewBox` too tight (content touching/clipped at the canvas edge, e.g. state diagrams with two-way labeled edges).

## 9. Design principles, stated explicitly

- **Verify with a rendered artifact, not just "did it throw."** A fix that stops an exception isn't necessarily correct — see §5's block-arrow label, which rendered without error for a long time while showing literal `&nbsp;&nbsp;&nbsp;` text instead of blank padding, and see §4's three silent-zero-bbox bugs, none of which raised anything either. The reliable check is comparing an actual rendered PNG (via the CLI) against what the diagram is supposed to look like, not just confirming `mermaid.render()` resolved.

- **Never patch `mermaid.js` itself.** Every fix lives in `dom_shim.js` or `engine.py`. This means upgrading to a new mermaid.js release is a file swap, not a rebase of hand-edits — at the cost of occasionally needing a small compensating patch (§2, mindmap centering) when mermaid.js's own generated output has a gap that only shows up for the native `<text>` elements mermaid.js emits regardless of `textPlacement` (journey/timeline section headers, mindmap nodes). Labels themselves use mermaid's default `htmlLabels:true`: novasvg paints `<foreignObject>` directly (the retired resvg could not, which is why this project used to force `htmlLabels:false`).
- **One font, two consumers.** `font_metrics.py` and `raster.py` are handed the *same* DejaVu Sans font file *and* the same engine (novasvg). Layout (what mermaid.js's JS thinks a label's size is) and paint (what novasvg actually draws) agree by construction, not by coincidence — including `<foreignObject>` box heights, which come from `novasvg.fonts.measure_foreign_object()`, the very logic novasvg's painter uses.
- **Implement real geometry, not special cases.** Every fix in §4 replaced an approximation with the actual spec-defined behavior (real SVG arc math, real CSS cascade lookup, real transform composition) rather than a targeted patch for one failing sample — verified, each time, by testing against synthetic inputs unrelated to any sample diagram.