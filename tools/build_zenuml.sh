#!/usr/bin/env bash
# Builds mermaidx/assets/zenuml.js: the SVG renderer of ZenUML (@zenuml/core), bundled by esbuild into one script
# that defines `globalThis.__zenuml = { renderToSvg, setCanvasContext }`.
#
# Why this is not just @mermaid-js/mermaid-zenuml: that plugin renders HTML with React into a <foreignObject> and asks
# a browser how big it came out, which mermaidx's small DOM shim cannot do. The command line tool of @zenuml/core
# (dist/cli/zenuml.mjs) contains a renderer of its own, `renderToSvg(code, options)`: a parser, a layout and an SVG
# writer, no React and no DOM except for measuring text with a canvas (which the shim has). It is not exported, so
# this script takes that file, cuts off the command line part (files, arguments, rasterizing) and bundles the rest.
# The cut is checked: if a future version of @zenuml/core changes the file, the build stops instead of guessing.
#
# mermaidx evaluates the result only for a diagram that starts with `zenuml`, see `needs_zenuml()` in
# mermaidx/engines/_common.py.
#
# Needs node and npm. Usage: tools/build_zenuml.sh [version]   (default: the version pinned below)
set -euo pipefail

VERSION="${1:-3.50.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$WORK"
npm init -y >/dev/null
npm install --silent "@zenuml/core@${VERSION}" esbuild

# antlr4 imports `fs` for its FileStream, which is not used here: an empty module stands in for it.
echo "export default {}; export const readFileSync = () => { throw new Error('no fs'); };" > empty_fs.mjs

node --input-type=module - <<'JS'
import { readFileSync, writeFileSync } from "node:fs";

const cli = "node_modules/@zenuml/core/dist/cli/zenuml.mjs";
let src = readFileSync(cli, "utf8");
if (src.startsWith("#!")) src = src.slice(src.indexOf("\n") + 1);
src = src.replace(/^import .*["']node:(fs|path)["'];?\n/gm, "");

// the command line part starts at the first of these (renderToSvg, composeSvg and escXml come before them)
const markers = ["function readVersion", "function printHelp", "function extractZenumlBlocks", "function rasterizeToPng", "function parseArgs", "async function main()"];
const found = markers.map((m) => src.indexOf(m)).filter((i) => i !== -1);
if (found.length === 0) throw new Error("none of the command line markers was found: the file changed, check this script");
let head = src.slice(0, Math.min(...found));
head = head.slice(0, head.lastIndexOf("\n"));

for (const needed of ["function renderToSvg(", "function composeSvg(", "function escXml(", "setCanvasContext"]) {
  if (!head.includes(needed)) throw new Error(`"${needed}" is not in the part that was kept: the file changed, check this script`);
}
if (/\bfrom ['"]node:/.test(head) || /\bprocess\.(argv|stdout|stderr|exit)\b/.test(head)) {
  throw new Error("node-only code is left in the part that was kept: the file changed, check this script");
}
writeFileSync("entry.mjs", head + "\nglobalThis.__zenuml = { renderToSvg, setCanvasContext };\n");
JS

# the entry has to sit next to the CLI file so that antlr4 and marked resolve from the package's node_modules
cp entry.mjs node_modules/@zenuml/core/dist/cli/_entry.mjs
npx esbuild node_modules/@zenuml/core/dist/cli/_entry.mjs --bundle --format=iife --minify --platform=neutral \
  --main-fields=module,main --alias:fs=./empty_fs.mjs \
  --banner:js="/* @zenuml/core ${VERSION} renderToSvg (from dist/cli/zenuml.mjs), bundled by tools/build_zenuml.sh. Do not edit. */" \
  --log-level=error --outfile="$ROOT/mermaidx/assets/zenuml.js"

echo "wrote mermaidx/assets/zenuml.js ($(wc -c < "$ROOT/mermaidx/assets/zenuml.js") bytes)"
