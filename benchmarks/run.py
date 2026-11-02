#!/usr/bin/env python3
"""Render every sample with mmdc and every mermaidx backend, and record the time.

Writes, under --out:
    results.json                      timings, status, versions, machine
    png/<sample>/<renderer>.png       the rendered image
    mmd/<sample>.mmd                  the Mermaid source, for the download button

The clock covers Mermaid text -> PNG. mermaidx is called as a library (warm,
median of --repeats); mmdc is started once per run (median of --mmdc-repeats),
so its time includes starting Node.js and Chrome. See docs/docs/benchmarks-method.md.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WARMUP_SOURCE = "flowchart LR\n    A --> B"
BACKGROUND = "#ffffff"


def png_size(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    return struct.unpack(">II", data[16:24])


def diagram_type(source: str) -> str:
    text = source.lstrip()
    if text.startswith("---"):  # skip front matter
        parts = text.split("---", 2)
        text = parts[2] if len(parts) == 3 else text
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("%%"):
            return re.split(r"[\s;:{(]", line, maxsplit=1)[0] or "unknown"
    return "unknown"


def short_error(exc: BaseException) -> str:
    msg = " ".join(str(exc).split()) or type(exc).__name__
    return f"{type(exc).__name__}: {msg}"[:300]


def command_output(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:
        return None


def cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


# --------------------------------------------------------------------------- mermaidx


class BackendUnavailable(RuntimeError):
    """The backend is installed but cannot render on this machine."""


def renderer_label(name):
    """What the page shows for a mermaidx renderer: `<backend> | <engine>` for js backends, the backend for rust."""
    if name in ("quickjs", "v8"):
        return f"js:mermaid | {name}"
    if name.startswith("pele-"):
        return f"js:pele | {name[len('pele-'):]}"
    return f"rust:{name}"


def mermaidx_renderers():
    """The mermaidx renderers that can run here, as {name: render() keywords}.

    The names are the ones the docs site knows (the ids `mermaidx-quickjs`, `mermaidx-v8`, ...), so the js:mermaid
    ones stay as they were before backends became `<kind>:<name>` with a separate `engine`. js:pele gets the same
    two, as `pele-quickjs` and `pele-v8`."""
    import mermaidx

    engines = mermaidx.available_engines()
    renderers = {}
    for engine in engines:
        renderers[engine] = {"backend": "js:mermaid", "engine": engine}
    for engine in engines:
        renderers[f"pele-{engine}"] = {"backend": "js:pele", "engine": engine}
    for backend in mermaidx.backends():
        kind, _, name = backend.partition(":")
        if kind == "rust":
            renderers[name] = {"backend": backend}
    return renderers


def run_mermaidx_backend(backend, render_kwargs, samples, out_dir, repeats, log):
    """Times every sample (PNG, `repeats` runs) and, when `<sample>.svg` sits next to it as the mermaid-cli
    reference, also records how many of its words the SVG of this renderer has (`labels`)."""
    import mermaidx

    def render_png(source):
        return mermaidx.render(source, **render_kwargs).png(background=BACKGROUND)

    try:
        t0 = time.perf_counter()
        render_png(WARMUP_SOURCE)
        startup_ms = (time.perf_counter() - t0) * 1000
        render_png(WARMUP_SOURCE)
    except Exception as exc:
        raise BackendUnavailable(short_error(exc)) from exc

    results = {}
    for sample in samples:
        source = sample.read_text(encoding="utf-8")
        runs, data = [], None
        try:
            for _ in range(repeats):
                t = time.perf_counter()
                data = render_png(source)
                runs.append((time.perf_counter() - t) * 1000)
            if not data:
                raise RuntimeError("renderer returned no image")
            results[sample.stem] = ok_result(sample.stem, f"mermaidx-{backend}", data, runs, out_dir)
            reference = sample.with_suffix(".svg")
            if reference.is_file():
                svg = mermaidx.render(source, **render_kwargs).svg()
                results[sample.stem]["labels"] = label_recall(svg, reference.read_text(encoding="utf-8"))
            log(f"  {sample.stem:<34} {results[sample.stem]['time_ms']:>8.1f} ms")
        except Exception as exc:  # unsupported diagram, engine error, ...
            results[sample.stem] = {"status": "error", "error": short_error(exc)}
            log(f"  {sample.stem:<34} error: {results[sample.stem]['error'][:70]}")
    return startup_ms, results


# --------------------------------------------------------------------------- mmdc


def run_mmdc(samples, out_dir, repeats, puppeteer_config, log):
    mmdc = shutil.which("mmdc")
    if not mmdc:
        raise RuntimeError("mmdc not found on PATH")
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "out.png"
        base = [mmdc, "-b", BACKGROUND, "-q"]
        if puppeteer_config:
            base += ["-p", str(puppeteer_config)]

        t0 = time.perf_counter()
        warm_in = Path(tmp) / "warmup.mmd"
        warm_in.write_text(WARMUP_SOURCE)
        subprocess.run(base + ["-i", str(warm_in), "-o", str(target)], capture_output=True, timeout=180)
        startup_ms = (time.perf_counter() - t0) * 1000

        for sample in samples:
            runs, data, error = [], None, None
            for _ in range(repeats):
                if target.exists():
                    target.unlink()
                t = time.perf_counter()
                try:
                    proc = subprocess.run(
                        base + ["-i", str(sample), "-o", str(target)],
                        capture_output=True, text=True, timeout=180,
                    )
                except subprocess.TimeoutExpired:
                    error = "TimeoutExpired: no result after 180 s"
                    break
                elapsed = (time.perf_counter() - t) * 1000
                if proc.returncode != 0 or not target.exists():
                    error = " ".join((proc.stderr or proc.stdout or "mmdc failed").split())[:300]
                    break
                runs.append(elapsed)
                data = target.read_bytes()
            if error or not data:
                results[sample.stem] = {"status": "error", "error": error or "no image"}
                log(f"  {sample.stem:<34} error: {(error or '')[:70]}")
            else:
                results[sample.stem] = ok_result(sample.stem, "mmdc", data, runs, out_dir)
                log(f"  {sample.stem:<34} {results[sample.stem]['time_ms']:>8.1f} ms")
    return startup_ms, results


# --------------------------------------------------------------------------- shared


# --------------------------------------------------------------------------- what is installed

def tree_size(path: Path) -> int:
    """Bytes of all the files under `path` (bytecode caches left out)."""
    total = 0
    for p in path.rglob("*"):
        with contextlib.suppress(OSError):
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
                total += p.stat().st_size
    return total


def dist_size(name):
    """Bytes on disk of an installed distribution, or None if it is not installed."""
    from importlib import metadata

    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None
    total = 0
    for f in dist.files or []:
        with contextlib.suppress(OSError):
            path = dist.locate_file(f)
            if path.is_file():
                total += path.stat().st_size
    return total or None


# the Python package that holds each mermaidx renderer's engine
ENGINE_DIST = {"quickjs": "quickjs-ng", "v8": "mini-racer", "merman": "mmdr", "mermaid-rs-renderer": "mmdr"}


def mermaidx_footprint(name):
    """What `pip install` puts on disk for a mermaidx renderer: mermaidx (the package holds the JavaScript of every
    backend, whichever is used), novasvg (the PNG output) and the engine. `js_bytes` is the JavaScript one render
    loads into the engine."""
    import mermaidx

    engine = ENGINE_DIST.get(name.removeprefix("pele-"))
    own = tree_size(Path(mermaidx.__file__).parent)
    parts = [{"name": "mermaidx, with the JavaScript of every backend", "bytes": own},
             {"name": "novasvg (PNG output)", "bytes": dist_size("novasvg")}]
    if engine:
        parts.append({"name": engine, "bytes": dist_size(engine)})
    parts = [part for part in parts if part["bytes"]]
    out = {"bytes": sum(part["bytes"] for part in parts), "parts": parts}
    library = "pele" if name.startswith("pele-") else "mermaid"
    if name in ("quickjs", "v8", "pele-quickjs", "pele-v8"):
        with contextlib.suppress(Exception):
            from mermaidx.engines import _common

            out["js_bytes"] = sum(len(script.encode("utf-8")) for script in _common.context_scripts(library))
    return out


def mmdc_footprint():
    """mermaid-cli with everything it installed under node_modules, plus the Chromium that puppeteer downloaded.
    Node.js itself is not counted."""
    exe = shutil.which("mmdc")
    if not exe:
        return None
    parts = []
    root = next((p for p in Path(exe).resolve().parents if p.name == "node_modules"), None)
    if root:
        parts.append({"name": "mermaid-cli and its node_modules", "bytes": tree_size(root)})
    cache = Path(os.environ.get("PUPPETEER_CACHE_DIR") or Path.home() / ".cache" / "puppeteer")
    if cache.is_dir():
        parts.append({"name": "Chromium (puppeteer cache)", "bytes": tree_size(cache)})
    parts = [part for part in parts if part["bytes"]]
    return {"bytes": sum(part["bytes"] for part in parts), "parts": parts} if parts else None


# --------------------------------------------------------------------------- render_many()

MIN_SAMPLES_FOR_SCALING = 3


def measure_scaling(names, available, per_renderer, sources, *, items, repeats, log):
    """How much faster does render_many() get with more worker processes? Mermaid text -> SVG (that is what the
    workers do) for `items` diagrams, the ones in the middle of the renderer's own timings, so that one slow diagram
    does not decide the result. Returns None when there is nothing to measure."""
    import mermaidx

    cores = os.cpu_count() or 1
    counts = sorted({w for w in (1, 2, 4, 8, cores) if w <= max(cores, 2)})
    series = []
    for name in names:
        results = per_renderer.get(f"mermaidx-{name}", {})
        done = {stem: r for stem, r in results.items() if r and r.get("status") == "ok"}
        if len(done) < MIN_SAMPLES_FOR_SCALING:
            continue
        middle = sorted(done, key=lambda stem: done[stem]["time_ms"])
        quarter = len(middle) // 4
        middle = middle[quarter:len(middle) - quarter][:8]
        batch = [sources[middle[i % len(middle)]] for i in range(items)]
        log(f"  render_many, {items} diagrams, {renderer_label(name)}")
        points = []
        try:
            for workers in counts:
                runs = []
                for _ in range(repeats):
                    t = time.perf_counter()
                    mermaidx.render_many(batch, workers=workers, **available[name])
                    runs.append((time.perf_counter() - t) * 1000)
                points.append({"workers": workers, "ms": round(statistics.median(runs), 1)})
                log(f"    {workers} worker(s): {points[-1]['ms']:>9.1f} ms")
        except Exception as exc:
            log(f"    skipped: {short_error(exc)}")
            continue
        for point in points:
            point["speedup"] = round(points[0]["ms"] / point["ms"], 2)
        series.append({"id": f"mermaidx-{name}", "label": renderer_label(name), "points": points})
    return {"items": items, "cores": cores, "repeats": repeats, "series": series} if series else None


# --------------------------------------------------------------------------- do the labels come out

def svg_words(svg: str) -> set:
    """The words a picture says: the text of an SVG, without its style, script, title and description."""
    import html

    svg = re.sub(r"<(style|script|title|desc)\b.*?</\1>", " ", svg, flags=re.DOTALL | re.IGNORECASE)
    return set(re.findall(r"\w+", html.unescape(re.sub(r"<[^>]+>", " ", svg)).lower()))


def label_recall(svg: str, reference_svg: str):
    """The share of the words of the reference picture (mermaid-cli's, kept in tests/samples) that the picture
    also has: 1.0 when every label is there, whatever the layout, the font or the colors. A renderer that draws a
    diagram type it does not know as a generic picture, or leaves the labels out, shows up here. None when the
    reference has no words."""
    ref = svg_words(reference_svg)
    return round(len(ref & svg_words(svg)) / len(ref), 3) if ref else None


def ok_result(sample_id, renderer_id, data, runs, out_dir):
    path = out_dir / "png" / sample_id / f"{renderer_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    width, height = png_size(data)
    return {
        "status": "ok",
        "time_ms": round(statistics.median(runs), 2),
        "runs_ms": [round(r, 2) for r in runs],
        "png": f"png/{sample_id}/{renderer_id}.png",
        "width": width,
        "height": height,
        "bytes": len(data),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=Path, default=ROOT / "tests" / "samples")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "static" / "benchmarks")
    ap.add_argument("--repeats", type=int, default=5, help="timed runs per sample for mermaidx")
    ap.add_argument("--mmdc-repeats", type=int, default=3, help="timed runs per sample for mmdc")
    ap.add_argument("--only", action="append", help="sample name (repeatable)")
    ap.add_argument("--skip-mmdc", action="store_true")
    ap.add_argument("--scaling-items", type=int, default=16,
                    help="diagrams for the render_many() measurement, 0 to skip it (default: 16)")
    ap.add_argument("--scaling-repeats", type=int, default=3, help="timed runs per worker count (default: 3)")
    ap.add_argument("--backend", action="append", help="mermaidx renderer: quickjs, v8, pele-quickjs, pele-v8, merman or mermaid-rs-renderer "
                                      "(repeatable; default: all available)")
    ap.add_argument("--puppeteer-config", type=Path, help="JSON file passed to mmdc -p (e.g. --no-sandbox)")
    args = ap.parse_args(argv)

    import mermaidx

    def log(msg):
        print(msg, flush=True)

    samples = sorted(args.samples.glob("*.mmd"))
    if args.only:
        samples = [s for s in samples if s.stem in set(args.only)]
    if not samples:
        sys.exit(f"no .mmd samples found in {args.samples}")

    args.out.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(args.out / "png", ignore_errors=True)
    shutil.rmtree(args.out / "mmd", ignore_errors=True)
    (args.out / "mmd").mkdir(parents=True)
    for s in samples:
        shutil.copyfile(s, args.out / "mmd" / s.name)

    renderers, per_renderer, skipped = [], {}, []

    def skip(rid, label, msg):
        log(f"  skipped: {msg}")
        skipped.append({"id": rid, "label": label, "error": msg})
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title=Benchmark::{label} was skipped: {msg}", flush=True)

    if not args.skip_mmdc:
        log("mmdc")
        try:
            startup, res = run_mmdc(samples, args.out, args.mmdc_repeats, args.puppeteer_config, log)
            renderers.append({"id": "mmdc", "label": "@mermaid-js/mermaid-cli", "kind": "browser", "startup_ms": round(startup, 1),
                              "version": command_output(["mmdc", "--version"])})
            per_renderer["mmdc"] = res
        except Exception as exc:
            skip("mmdc", "@mermaid-js/mermaid-cli", short_error(exc))

    available = mermaidx_renderers()
    for backend in args.backend or available:
        if backend not in available:
            log(f"mermaidx {backend}")
            skip(f"mermaidx-{backend}", renderer_label(backend), "backend not available in this environment")
            continue
        rid = f"mermaidx-{backend}"
        log(rid)
        try:
            startup, res = run_mermaidx_backend(backend, available[backend], samples, args.out, args.repeats, log)
        except BackendUnavailable as exc:
            skip(rid, renderer_label(backend), str(exc))
            continue
        renderers.append({"id": rid, "label": renderer_label(backend), "kind": "library",
                          "startup_ms": round(startup, 1), "version": mermaidx.__version__})
        per_renderer[rid] = res

    if not renderers:
        sys.exit("no renderer produced any result, see the messages above")

    sources = {s.stem: s.read_text(encoding="utf-8") for s in samples}

    footprint = {}
    for r in renderers:
        info = mmdc_footprint() if r["id"] == "mmdc" else mermaidx_footprint(r["id"].removeprefix("mermaidx-"))
        if info:
            footprint[r["id"]] = info

    scaling = None
    if args.scaling_items > 0:
        log("render_many")
        ids = ("mermaidx-quickjs", "mermaidx-pele-quickjs")
        names = [r["id"].removeprefix("mermaidx-") for r in renderers if r["id"] in ids]
        scaling = measure_scaling(names, available, per_renderer, sources,
                                  items=args.scaling_items, repeats=args.scaling_repeats, log=log)

    def version(pkg):
        try:
            from importlib.metadata import version as v
            return v(pkg)
        except Exception:
            return None

    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commit": os.environ.get("GITHUB_SHA") or command_output(["git", "rev-parse", "HEAD"]),
            "ref": os.environ.get("GITHUB_REF_NAME"),
            "repeats": args.repeats,
            "mmdc_repeats": args.mmdc_repeats,
            "background": BACKGROUND,
            "machine": {"cpu": cpu_name(), "cores": os.cpu_count(), "os": platform.platform(),
                        "python": platform.python_version(), "node": command_output(["node", "--version"])},
            "versions": {"mermaidx": mermaidx.__version__, "novasvg": version("novasvg"),
                         "mmdc": command_output(["mmdc", "--version"]) if not args.skip_mmdc else None},
            "renderers": renderers,
            "skipped": skipped,
        },
        "footprint": footprint,
        "scaling": scaling,
        "samples": [
            {
                "id": s.stem,
                "title": re.sub(r"^\d+_", "", s.stem).replace("_", " "),
                "type": diagram_type(sources[s.stem]),
                "chars": len(sources[s.stem]),
                "source": f"mmd/{s.name}",
                "results": {r["id"]: per_renderer[r["id"]].get(s.stem) for r in renderers},
            }
            for s in samples
        ],
    }
    (args.out / "results.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    log(f"\nwrote {args.out / 'results.json'}")


if __name__ == "__main__":
    main()
