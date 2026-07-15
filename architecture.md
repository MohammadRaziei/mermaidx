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
        ENG -- "measureText / getBBox\npathBBox callbacks" --> FM["font_metrics.py\n(DejaVu Sans glyph widths)"]
        ENG --> RAST["raster.py\n(resvg)"]
        RAST --> OUT["PNG / PDF / numpy"]
    end
    subgraph qjs["QuickJS-ng context (one dedicated thread)"]
        SHIM["dom_shim.js\nfake DOM / CSSOM / Canvas2D"]
        MMD["mermaid.js v11\n(unmodified, ~6MB)"]
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
    participant R as resvg (raster.py)

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
        S->>E: __measureTextFull_raw(text, size, family, weight)
        E->>E: font_metrics.py measures against<br/>the same DejaVu Sans file resvg uses
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
- **The Promise chain has to be pumped manually** (`_pump_jobs`). QuickJS has no event loop of its own; `execute_pending_job()` runs one microtask at a time, and `Engine` calls it in a loop until the result is ready. Early on this loop had no early-exit condition and would drain a diagram type's entire internal animation-frame queue (hundreds of thousands of no-op iterations) even after the real answer was ready — see §5.

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
| `__getCssRules()` / `__resolveCssProp(el, prop)` | A tiny CSS parser + the same selector engine used for `querySelector`, reused to answer "what would `getComputedStyle` say" for the handful of properties mermaid's *layout* code actually reads (as opposed to properties that only affect paint, which resvg handles natively). |
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
    POS --> MEAS["__measureTextFull(text, font)\n→ Python → font_metrics.py\n(real DejaVu Sans glyph widths,\nsame file resvg paints with)"]
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

## 5. Async without a browser: the job-pump model

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

## 6. Where the layers hand off

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
    DIAG -->|".png() / .pdf() / .numpy()"| RASTER["raster.py → resvg\n(same DejaVu Sans font file\nas font_metrics.py, so layout\nand paint agree by construction)"]
    DIAG -->|".ascii()"| ASCII["ascii.py → termaid"]
    RASTER --> PNGOUT["PNG bytes"]
    RASTER --> PDFOUT["pdf_writer.py\n→ PDF bytes"]
    RASTER --> NPOUT["numpy array"]
```

`backends.py` sits alongside this as a pluggable second path: if the optional `mmdr` (native-Rust) package is installed, its backends (`merman`, `mermaid-rs-renderer`) are picked up automatically, each producing its own `.svg()`  — everything downstream of that (`.png()`, `.pdf()`, `.numpy()`) still goes through *this* project's `raster.py`/`pdf_writer.py`, since `DiagramBase` implements those once, shared by every backend.

---

## 7. File reference

| File | Responsibility |
|---|---|
| `mermaidx/engine.py` | Owns the QuickJS context (one per process, one dedicated thread). Wires up the Python↔JS callback bridge (`__measureText`, `__measureTextFull`, `__pathBBox`). Implements `_path_bbox`/`_arc_extrema` (real SVG path geometry). Drives the job-pump loop. Applies the small set of documented post-render CSS patches. |
| `mermaidx/assets/dom_shim.js` | The fake DOM/CSSOM/Canvas2D. `Node`/`Element`/`Document`/`TextNode`/`CSSStyleDecl`/`ClassList`. The `getBBox()` dispatch (§4). The CSS selector engine (`__matches`/`__matchesCompound`). The Canvas 2D stub. Timer/event polyfills. |
| `mermaidx/assets/mermaid.js` | mermaid.js v11, unmodified, bundled via esbuild. Never patched directly — every gap is compensated for in the shim or engine.py instead, so upgrading this file doesn't mean re-auditing hand-edits. |
| `mermaidx/font_metrics.py` | Reads real glyph advance widths from a bundled DejaVu Sans font file. The *only* source of text-measurement truth, shared by both the shim's `getBBox()` and (indirectly, via the same font file) resvg's final paint. |
| `mermaidx/raster.py` | SVG → PNG via resvg, using that same font file. |
| `mermaidx/pdf_writer.py` | PNG → PDF, hand-written (not resvg). |
| `mermaidx/diagram.py` | `DiagramBase`/`Diagram`/`DiagramRust` — the lazy, cached public object `render()` returns. |
| `mermaidx/backends.py` | Discovers optional `mmdr`-provided backends. |
| `mermaidx/ascii.py` | SVG → ASCII/Unicode art via `termaid`. |
| `tests/test_samples.py` | Structural checks (label text, aspect ratio) *and* geometry/pixel checks (content not clipped, shapes painted before labels, labels not stacked on siblings, label ink pixel-centered in its shape) — the geometry/pixel checks exist specifically because the structural ones are provably blind to whole classes of real rendering bugs. |

---

## 8. Design principles, stated explicitly

- **Never patch `mermaid.js` itself.** Every fix lives in `dom_shim.js` or `engine.py`. This means upgrading to a new mermaid.js release is a file swap, not a rebase of hand-edits — at the cost of occasionally needing a small compensating patch (§2, mindmap centering) when mermaid.js's own generated output has a gap that only shows up in the non-default (`htmlLabels:false`) configuration this project requires (`resvg` can't render `foreignObject`+HTML content, so `htmlLabels:false` isn't optional here).
- **One font, two consumers.** `font_metrics.py` and `raster.py` are handed the *same* DejaVu Sans font file. Layout (what mermaid.js's JS thinks a label's size is) and paint (what resvg actually draws) agree by construction, not by coincidence.
- **Implement real geometry, not special cases.** Every fix in §4 replaced an approximation with the actual spec-defined behavior (real SVG arc math, real CSS cascade lookup, real transform composition) rather than a targeted patch for one failing sample — verified, each time, by testing against synthetic inputs unrelated to any sample diagram.
