#!/usr/bin/env bash
# Builds mermaidx/assets/layout_elk.js: the ELK layout of Mermaid (@mermaid-js/layout-elk, which contains elkjs),
# bundled by esbuild into one script that registers itself on the `mermaid` global.
#
# mermaidx evaluates that script only for a diagram that asks for ELK (`flowchart-elk`, `layout: elk`, ...), see
# `needs_elk()` in mermaidx/engines/_common.py.
#
# Needs node and npm. Usage: tools/build_layout_elk.sh [version]   (default: the version pinned below)
set -euo pipefail

VERSION="${1:-1.0.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$WORK"
npm init -y >/dev/null
npm install --silent "@mermaid-js/layout-elk@${VERSION}" esbuild

# `mermaid` is the global that mermaidx's engines create after loading mermaid.js.
cat > entry.mjs <<'JS'
import loaders from "@mermaid-js/layout-elk";
globalThis.mermaid.registerLayoutLoaders(loaders);
JS

npx esbuild entry.mjs --bundle --format=iife --minify --platform=neutral --main-fields=module,main \
  --banner:js="/* @mermaid-js/layout-elk ${VERSION} (elkjs), bundled by tools/build_layout_elk.sh. Do not edit. */" \
  --log-level=error --outfile="$ROOT/mermaidx/assets/layout_elk.js"

echo "wrote mermaidx/assets/layout_elk.js ($(wc -c < "$ROOT/mermaidx/assets/layout_elk.js") bytes)"
