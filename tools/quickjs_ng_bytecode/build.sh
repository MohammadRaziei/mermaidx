#!/usr/bin/env bash
# Builds the wheel of the `quickjs-ng` package with `Context.compile()` and `Context.eval_bytecode()` added.
#
#   tools/quickjs_ng_bytecode/build.sh [output-dir]      (default: tools/quickjs_ng_bytecode/dist)
#   pip install tools/quickjs_ng_bytecode/dist/quickjs_ng-*.whl
#
# It downloads the source of quickjs-ng $VERSION from PyPI, puts module.c (this directory's, the only file that
# differs) in its place, and builds it. See README.md.
set -euo pipefail

VERSION="0.18.0.1"
here="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$here/dist}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python -m pip download "quickjs-ng==$VERSION" --no-binary :all: --no-deps -d "$work" -q
tar xzf "$work/quickjs_ng-$VERSION.tar.gz" -C "$work"
cp "$here/module.c" "$work/quickjs_ng-$VERSION/module.c"
python -m pip wheel "$work/quickjs_ng-$VERSION" --no-deps -w "$out" -q
ls -1 "$out"/quickjs_ng-*.whl
