#!/usr/bin/env python3
"""Render every sample with mmdc and every mermaidx backend, and record the time.

Writes, under --out:
    results.json                      timings, status, versions, machine
    png/<sample>/<renderer>.png       the rendered image

The clock covers Mermaid text -> PNG. mermaidx is called as a library (warm,
median of --repeats); mmdc is started once per run (median of --mmdc-repeats),
so its time includes starting Node.js and Chrome. See docs/docs/benchmarks-method.md.
"""
from __future__ import annotations

import argparse
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


def run_mermaidx_backend(backend, samples, out_dir, repeats, log):
    import mermaidx

    def render_png(source):
        return mermaidx.render(source, backend=backend).png(background=BACKGROUND)

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
    ap.add_argument("--backend", action="append", help="mermaidx backend (repeatable; default: all available)")
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
            renderers.append({"id": "mmdc", "label": "mmdc", "kind": "browser", "startup_ms": round(startup, 1),
                              "version": command_output(["mmdc", "--version"])})
            per_renderer["mmdc"] = res
        except Exception as exc:
            skip("mmdc", "mmdc", short_error(exc))

    available = mermaidx.backends()
    for backend in args.backend or available:
        if backend not in available:
            log(f"mermaidx {backend}")
            skip(f"mermaidx-{backend}", f"mermaidx {backend}", "backend not available in this environment")
            continue
        rid = f"mermaidx-{backend}"
        log(rid)
        try:
            startup, res = run_mermaidx_backend(backend, samples, args.out, args.repeats, log)
        except BackendUnavailable as exc:
            skip(rid, f"mermaidx {backend}", str(exc))
            continue
        renderers.append({"id": rid, "label": f"mermaidx {backend}", "kind": "library",
                          "startup_ms": round(startup, 1), "version": mermaidx.__version__})
        per_renderer[rid] = res

    if not renderers:
        sys.exit("no renderer produced any result, see the messages above")

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
        "samples": [
            {
                "id": s.stem,
                "title": re.sub(r"^\d+_", "", s.stem).replace("_", " "),
                "type": diagram_type(s.read_text(encoding="utf-8")),
                "results": {r["id"]: per_renderer[r["id"]].get(s.stem) for r in renderers},
            }
            for s in samples
        ],
    }
    (args.out / "results.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    log(f"\nwrote {args.out / 'results.json'}")


if __name__ == "__main__":
    main()
