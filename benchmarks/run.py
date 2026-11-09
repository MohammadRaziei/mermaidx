#!/usr/bin/env python3
"""Render every sample with mmdc and every mermaidx backend, and record the time.

Writes, under --out:
    results.json                      timings, status, versions, machine
    png/<sample>/<renderer>.png       the rendered image, recompressed without loss (see optimize_png)
    mmd/<sample>.mmd                  the Mermaid source, for the download button

Samples come from tests/samples (each has a mermaid-cli reference .svg) and from benchmarks/samples (diagrams that
only the benchmark uses, with no reference: ELK layout and ZenUML, which tests/samples cannot hold because its tests
need a reference for every sample). A renderer that cannot draw a diagram is recorded as an error, not left out:
the page shows it as "Not supported" with the message.

The clock covers Mermaid text -> PNG. mermaidx is called as a library (warm,
median of --repeats); mmdc is started once per run (median of --mmdc-repeats),
so its time includes starting Node.js and Chrome. See docs/docs/benchmarks-method.md.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:  # optional: measures the download size of each renderer (download_footprint)
    import pip_size
except ImportError:
    pip_size = None

ROOT = Path(__file__).resolve().parent.parent
WARMUP_SOURCE = "flowchart LR\n    A --> B"
SAMPLE_DIRS = (ROOT / "tests" / "samples", ROOT / "benchmarks" / "samples")
BACKGROUND = "#ffffff"
# oxipng effort for the stored copy of every PNG: 2 takes about 0.2 s per image and halves a typical diagram, 4 gains
# only ~2 points more for 7x the time. Settable with --png-level; lowered to None by --no-optimize-png.
DEFAULT_PNG_LEVEL = 2
PNG_LEVEL = DEFAULT_PNG_LEVEL


def png_size(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    return struct.unpack(">II", data[16:24])


def optimize_png(data: bytes, level=None) -> bytes:
    """The PNG recompressed without loss (same pixels, same size), for the copy that goes on the web page.

    novasvg's encoder has no compression setting, and mmdc's output is not tuned either, so the files the page
    downloads are about twice what they need to be. This runs after the clock has stopped, and `bytes` in
    results.json stays the size of what the renderer produced, so the numbers do not change. Needs `pyoxipng`;
    without it (or with level None) the PNG is stored as it is."""
    level = PNG_LEVEL if level is None else level
    if level is None:
        return data
    try:
        import oxipng
    except ImportError:
        return data
    try:
        smaller = oxipng.optimize_from_memory(data, level=level, strip=oxipng.StripChunks.safe())
    except Exception:  # an optimizer failure must never cost the benchmark its image
        return data
    return smaller if len(smaller) < len(data) else data


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


def sample_feature(source: str):
    """"elk" for a diagram that asks for the ELK layout, "zenuml" for ZenUML, None for the rest. These are the
    two things mermaid.js does not do by itself, so the page lists them apart."""
    if diagram_type(source) == "zenuml":
        return "zenuml"
    try:
        needs_elk = importlib.import_module("mermaidx.engines._common").needs_elk
    except (ImportError, AttributeError):  # an older mermaidx without ELK
        return None
    return "elk" if needs_elk(source) else None


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
    """Times every sample (PNG, `repeats` runs)."""
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

# the extra that brings in the engine of each mermaidx renderer (the other renderers need none)
ENGINE_EXTRA = {"v8": "v8engine", "merman": "rust", "mermaid-rs-renderer": "rust"}
_wheel_cache = {}
HTTP_TIMEOUT = 60


def _warn(message: str) -> None:
    sys.stderr.write(f"download size: left out, {message}\n")


def mermaidx_download(name):
    """What a user downloads to `pip install` a mermaidx renderer, measured by pip-size.

    pip-size builds a wheel from this checkout (the working tree, with the extra that brings the renderer's engine)
    and adds the wheels of everything it depends on, looked up on PyPI. Returns None, so the page leaves the bar
    out, when pip-size is not installed, the build fails, or a dependency could not be looked up (the total would
    be too small). One build per extra, not per renderer."""
    if pip_size is None:
        return None
    extra = ENGINE_EXTRA.get(name.removeprefix("pele-"))
    if extra not in _wheel_cache:
        info = None
        try:
            res = pip_size.resolve(str(ROOT), extras=extra)
            if res.warnings:
                _warn(f"pip-size could not look up a dependency: {res.warnings[0]}")
            else:
                parts = [{"name": f"{pkg.name} {pkg.version}", "bytes": pkg.size} for pkg in res.packages]
                info = {"bytes": res.total_size, "parts": parts, "tool": f"pip-size {pip_size.__version__}"}
        except Exception as exc:  # a failed build or lookup must never cost the benchmark its other results
            _warn(f"pip-size: {short_error(exc)}")
        _wheel_cache[extra] = info
    return _wheel_cache[extra]


def js_bytes(name):
    """The JavaScript one render loads into the engine (all of mermaid.js, or much less for pele), or None."""
    library = "pele" if name.startswith("pele-") else "mermaid"
    if name.removeprefix("pele-") not in ("quickjs", "v8"):
        return None
    with contextlib.suppress(Exception):
        from mermaidx.engines import _common

        return sum(len(script.encode("utf-8")) for script in _common.context_scripts(library))
    return None


def remote_size(url, *, allow_download):
    """The size in bytes of the file at `url`: from Content-Length of a HEAD request. Some servers and proxies leave
    it out; then the file is downloaded and counted if `allow_download`, else the size is None."""
    # the URLs are https links from npm's lockfile and Chrome for Testing, never user input
    with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
        length = resp.headers.get("Content-Length")
    if length is not None:
        return int(length)
    if not allow_download:
        return None
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
        return len(resp.read())


# puppeteer's cache folders are named <platform>-<version>; Chrome for Testing names its downloads differently
CFT_PLATFORM = {"linux": "linux64", "mac": "mac-x64", "mac_arm": "mac-arm64", "win32": "win32", "win64": "win64"}


def chrome_downloads(root):
    """[(name, url)] of the browser archive mmdc runs on: chrome-headless-shell, because mermaid-cli launches puppeteer
    with `headless: "shell"`, in the revision pinned by the puppeteer that is installed under `root` (older versions
    left in the cache by earlier installs are not counted, and neither is the regular Chrome puppeteer also fetches
    but mmdc never starts). Empty when that revision is not in the puppeteer cache."""
    revisions = next(root.glob("puppeteer-core/lib/**/revisions.js"), None)
    pinned = r"'chrome-headless-shell':\s*'([\d.]+)'"
    found = re.search(pinned, revisions.read_text(encoding="utf-8")) if revisions else None
    cache = Path(os.environ.get("PUPPETEER_CACHE_DIR") or Path.home() / ".cache" / "puppeteer") / "chrome-headless-shell"
    if not found or not cache.is_dir():
        return []
    version = found.group(1)
    for folder in sorted(cache.glob(f"*-{version}")):
        cft = CFT_PLATFORM.get(folder.name.removesuffix(f"-{version}"))
        if cft:
            host = "https://storage.googleapis.com/chrome-for-testing-public"
            url = f"{host}/{version}/{cft}/chrome-headless-shell-{cft}.zip"
            return [(f"chrome-headless-shell {version} (puppeteer download)", url)]
    return []


def mmdc_download():
    """What `npm install` of mermaid-cli downloads: the tarball of every package npm installed (read from
    node_modules/.package-lock.json, which lists only what is on this machine, so other platforms' optional
    packages are not counted), plus the browser archive puppeteer fetches in its postinstall step. The sizes come
    from the registry and the Chrome for Testing server. None when mmdc is not an npm install, or when a size could
    not be had (the total would be too small)."""
    exe = shutil.which("mmdc")
    root = next((p for p in Path(exe).resolve().parents if p.name == "node_modules"), None) if exe else None
    lock = root / ".package-lock.json" if root else None
    if not lock or not lock.is_file():
        return None
    packages = [(path.removeprefix("node_modules/"), entry["resolved"], entry.get("version", ""))
                for path, entry in json.loads(lock.read_text(encoding="utf-8")).get("packages", {}).items()
                if entry.get("resolved")]
    try:
        with ThreadPoolExecutor(16) as pool:
            sizes = list(pool.map(lambda item: remote_size(item[1], allow_download=True), packages))
            browsers = chrome_downloads(root)
            browser_sizes = list(pool.map(lambda item: remote_size(item[1], allow_download=False), browsers))
    except Exception as exc:
        _warn(f"mmdc: {short_error(exc)}")
        return None
    if any(size is None for size in browser_sizes):
        _warn("mmdc: the size of the browser download is not known")
        return None
    if not browsers:
        _warn("mmdc: the browser puppeteer downloaded was not found in its cache, and the total would be without it")
        return None
    parts = [{"name": f"npm: {len(packages)} packages", "bytes": sum(sizes)}]
    parts += [{"name": name, "bytes": size} for (name, _), size in zip(browsers, browser_sizes)]
    return {"bytes": sum(part["bytes"] for part in parts), "parts": parts, "tool": "npm tarballs + Chrome for Testing"}


# --------------------------------------------------------------------------- render_many()

MIN_SAMPLES_FOR_SCALING = 3


def measure_scaling(
    names, available, per_renderer, sources, *, items, repeats, log, skip=(), executor="process",
):
    """How much faster does render_many() get with more workers (processes or threads, as `executor` says)? Mermaid
    text -> SVG (that is what the workers do) for `items` diagrams, the ones in the middle of the renderer's own
    timings, so that one slow diagram does not decide the result. The samples in `skip` (ELK and ZenUML, which load
    more JavaScript) are left out.
    Returns None when there is nothing to measure."""
    import mermaidx

    cores = os.cpu_count() or 1
    counts = sorted({w for w in (1, 2, 4, 8, cores) if w <= max(cores, 2)})
    series = []
    for name in names:
        results = per_renderer.get(f"mermaidx-{name}", {})
        done = {stem: r for stem, r in results.items() if r and r.get("status") == "ok" and stem not in skip}
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
                    # Every run starts its workers (render_many() does not keep them), as the first call of a
                    # program does.
                    mermaidx.render_many(batch, workers=workers, executor=executor, **available[name])
                    runs.append((time.perf_counter() - t) * 1000)
                points.append({"workers": workers, "ms": round(statistics.median(runs), 1)})
                log(f"    {workers} worker(s): {points[-1]['ms']:>9.1f} ms")
        except Exception as exc:
            log(f"    skipped: {short_error(exc)}")
            continue
        for point in points:
            point["speedup"] = round(points[0]["ms"] / point["ms"], 2)
        series.append({"id": f"mermaidx-{name}", "label": renderer_label(name), "points": points})
    if not series:
        return None
    return {"items": items, "cores": cores, "repeats": repeats, "executor": executor, "series": series}


def ok_result(sample_id, renderer_id, data, runs, out_dir):
    path = out_dir / "png" / sample_id / f"{renderer_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = optimize_png(data)
    path.write_bytes(stored)
    width, height = png_size(data)
    return {
        "status": "ok",
        "time_ms": round(statistics.median(runs), 2),
        "runs_ms": [round(r, 2) for r in runs],
        "png": f"png/{sample_id}/{renderer_id}.png",
        "width": width,
        "height": height,
        "bytes": len(data),
        "stored_bytes": len(stored),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", type=Path, action="append",
                    help="directory of .mmd samples (repeatable; default: tests/samples and benchmarks/samples)")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "static" / "benchmarks")
    ap.add_argument("--repeats", type=int, default=5, help="timed runs per sample for mermaidx")
    ap.add_argument("--mmdc-repeats", type=int, default=3, help="timed runs per sample for mmdc")
    ap.add_argument("--only", action="append", help="sample name (repeatable)")
    ap.add_argument("--skip-mmdc", action="store_true")
    ap.add_argument("--png-level", type=int, default=DEFAULT_PNG_LEVEL, choices=range(0, 7), metavar="0-6",
                    help="oxipng effort for the stored PNGs (default: %(default)s; needs pyoxipng)")
    ap.add_argument("--no-optimize-png", action="store_true", help="store the PNGs exactly as rendered")
    ap.add_argument("--scaling-items", type=int, default=16,
                    help="diagrams for the render_many() measurement, 0 to skip it (default: 16)")
    ap.add_argument("--scaling-repeats", type=int, default=3, help="timed runs per worker count (default: 3)")
    ap.add_argument("--scaling-executor", choices=("process", "thread"), default="process",
                    help="what the render_many() workers are (default: process, what the numbers have always "
                         "measured; thread is what render_many() uses by default)")
    ap.add_argument("--backend", action="append", help="mermaidx renderer: quickjs, v8, pele-quickjs, pele-v8, merman or mermaid-rs-renderer "
                                      "(repeatable; default: all available)")
    ap.add_argument("--puppeteer-config", type=Path, help="JSON file passed to mmdc -p (e.g. --no-sandbox)")
    args = ap.parse_args(argv)

    global PNG_LEVEL
    PNG_LEVEL = None if args.no_optimize_png else args.png_level

    import mermaidx

    def log(msg):
        print(msg, flush=True)

    sample_dirs = args.samples or [d for d in SAMPLE_DIRS if d.is_dir()]
    samples = sorted((s for d in sample_dirs for s in d.glob("*.mmd")), key=lambda s: s.stem)
    names = [s.stem for s in samples]
    if len(set(names)) != len(names):
        sys.exit("two samples have the same name: " + ", ".join(sorted({n for n in names if names.count(n) > 1})))
    if args.only:
        samples = [s for s in samples if s.stem in set(args.only)]
    if not samples:
        sys.exit("no .mmd samples found in " + ", ".join(str(d) for d in sample_dirs))

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
        if r["id"] == "mmdc":
            info = mmdc_download()
        else:
            name = r["id"].removeprefix("mermaidx-")
            info = mermaidx_download(name)
            if info and js_bytes(name):
                info["js_bytes"] = js_bytes(name)
        if info:
            footprint[r["id"]] = info

    scaling = None
    if args.scaling_items > 0:
        log("render_many")
        ids = ("mermaidx-quickjs", "mermaidx-pele-quickjs")
        names = [r["id"].removeprefix("mermaidx-") for r in renderers if r["id"] in ids]
        scaling = measure_scaling(names, available, per_renderer, sources,
                                  items=args.scaling_items, repeats=args.scaling_repeats, log=log,
                                  executor=args.scaling_executor,
                                  skip={stem for stem, text in sources.items() if sample_feature(text)})

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
                "feature": sample_feature(sources[s.stem]),
                "reference": s.with_suffix(".svg").is_file(),
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
