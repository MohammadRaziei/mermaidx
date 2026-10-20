---
title: Installation
sidebar_position: 1
description: Install mermaidx from PyPI. No Node.js, browser or compiler needed.
---

mermaidx is published on [PyPI](https://pypi.org/project/mermaidx) as prebuilt wheels. The base install has no system dependencies: no Node.js, no npm, no Chrome and no compiler.

```bash
pip install mermaidx
```

SVG, PNG, JPEG, PDF and ASCII output all work with the base install. Python 3.9 or newer is required.

## Optional extras

| Command | Adds |
| --- | --- |
| `pip install mermaidx[v8engine]` | The V8 engine (`mini-racer`) as `backend="v8"` |
| `pip install mermaidx[rust]` | The Rust backends `merman` and `mermaid-rs-renderer`, through [`mmdr`](https://github.com/mohammadraziei/mmdr) |
| `pip install numpy` | `Diagram.numpy()` |
| `pip install mermaidx[all]` | `v8engine`, `rust` and `numpy` together |

Check what is available at runtime:

```python
import mermaidx

print(mermaidx.backends())
# ['quickjs']                                      base install
# ['quickjs', 'v8']                                with mermaidx[v8engine]
# ['quickjs', 'merman', 'mermaid-rs-renderer']     with mermaidx[rust]
```

## Coming from `mmdc`

mermaidx was called `mmdc` until version 0.7.0. The old package is no longer updated. Uninstall it and install `mermaidx` instead; the module name changed from `mmdc` to `mermaidx` too.

> [!note]
> The upgrade to 0.10.0 has breaking changes: font embedding was removed, and `raster="resvg"` now raises a `ValueError`. See the [changelog](./CHANGELOG.md).
