# Notices: third-party software in mermaidx

mermaidx itself is MIT licensed (see `LICENSE.txt`). It ships JavaScript and font files made by other projects, bundled
without changes to their code (they are only minified or bundled with esbuild, see `tools/`). Their licenses are
below, and the license texts are in [`licenses/`](licenses/) (and, in the installed package, in
`mermaidx/licenses/`).

| File in `mermaidx/assets/` | Component | License | Source |
| --- | --- | --- | --- |
| `mermaid.js` | mermaid.js 12.3.0 (`dist/mermaid.min.js`) | MIT, [`mermaid-MIT.txt`](licenses/mermaid-MIT.txt) | https://github.com/mermaid-js/mermaid |
| `pele.js` | pele 1.13.0 (`dist/pele.js`) | MIT, [`pele-MIT.txt`](licenses/pele-MIT.txt) | https://www.npmjs.com/package/pele |
| `zenuml.js` | `renderToSvg` of @zenuml/core 3.50.1 | MIT, [`zenuml-core-MIT.txt`](licenses/zenuml-core-MIT.txt) | https://github.com/mermaid-js/zenuml-core |
| `zenuml.js` | antlr4 (JavaScript runtime) | BSD-3-Clause, [`antlr4-BSD-3-Clause.txt`](licenses/antlr4-BSD-3-Clause.txt) | https://github.com/antlr/antlr4 |
| `zenuml.js` | marked | MIT, [`marked-MIT.md`](licenses/marked-MIT.md) | https://github.com/markedjs/marked |
| `layout_elk.js` | @mermaid-js/layout-elk 1.0.1 | MIT, [`mermaid-layout-elk-MIT.txt`](licenses/mermaid-layout-elk-MIT.txt) | https://github.com/mermaid-js/mermaid |
| `layout_elk.js` | elkjs (the Eclipse Layout Kernel, compiled to JavaScript) | EPL-2.0, [`elkjs-EPL-2.0.md`](licenses/elkjs-EPL-2.0.md) | https://github.com/kieler/elkjs |
| `fonts/DejaVuSans*.ttf` | DejaVu Sans | Bitstream Vera license, public domain changes, [`LICENSE-DejaVu.txt`](mermaidx/assets/fonts/LICENSE-DejaVu.txt) | https://dejavu-fonts.github.io |

## Libraries inside those files

The files above are bundles, so they contain the libraries their authors depend on:

- `mermaid.js` contains the dependencies of mermaid.js, for example d3 and DOMPurify.
- `pele.js` is one file of pele.
- `layout_elk.js` contains, besides @mermaid-js/layout-elk and elkjs, d3 (ISC, and BSD-3-Clause for d3-ease), dagre-d3-es,
  dayjs, lodash-es and KaTeX (MIT) and DOMPurify (MPL-2.0 OR Apache-2.0).
- `zenuml.js` contains the renderer of @zenuml/core, which imports antlr4 and marked.

Each of them has its own license, which is the one in its npm package. mermaidx did not change any of them.

## elkjs (EPL-2.0)

`layout_elk.js` contains elkjs, which is distributed under the Eclipse Public License 2.0. It is used as it is, only
minified. Its source code is available at https://github.com/kieler/elkjs and from the `elkjs` package on npm. The EPL-2.0
license text is in [`licenses/elkjs-EPL-2.0.md`](licenses/elkjs-EPL-2.0.md). To get the exact
file mermaidx ships, run `tools/build_layout_elk.sh`.

## quickjs-ng (MIT)

`tools/quickjs_ng_bytecode/module.c` is the `module.c` of the `quickjs-ng` Python package 0.18.0.1 with two methods added
to `Context` (see the README in that directory). It is not part of the wheel. The license of the package is in
[`licenses/quickjs-ng-MIT.txt`](licenses/quickjs-ng-MIT.txt).
