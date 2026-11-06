"""Compiled QuickJS bytecode of the big bundled scripts, so a fresh context does not have to parse them again.

Every render gets a context of its own (see _common.reuses_context), and building one is almost all parsing:
QuickJS compiles every function of a script when it loads it, so `mermaid.js` (5.5 MB) takes about 800 ms to
evaluate, of which running its top level is a few. Loading the same script as bytecode takes about 100 ms.

The bytecode is made once, by the first context that needs it, and kept in memory and in a file in the user's cache
directory (so the next process, a command line call for one diagram, starts with it). It needs `Context.compile`
and `Context.eval_bytecode`, which the `quickjs-ng` package does not have yet (see third_party/quickjs-ng-bytecode);
without them every function here does what `ctx.eval(source)` does, just as before.

A file in the cache is trusted only when it has the header of this module, the checksum of its own bytes, and was
made by the same QuickJS (its bytecode version) from the same source: anything else is made again, never run.
Set `MERMAIDX_BYTECODE_CACHE=0` to switch bytecode off, and `MERMAIDX_CACHE_DIR` to put the files elsewhere.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

# Below this a script parses in a few milliseconds, and a cache file would cost more than it saves.
MIN_SOURCE_CHARS = 200_000
_MAGIC = b"MXQBC1\n"
_HASH_BYTES = 32

_lock = threading.Lock()
_memory: dict[str, bytes | None] = {}


def enabled() -> bool:
    return os.environ.get("MERMAIDX_BYTECODE_CACHE", "1").lower() not in ("0", "false", "no", "off")


def supported(ctx) -> bool:
    """True when the QuickJS binding can make and run bytecode."""
    return hasattr(ctx, "compile") and hasattr(ctx, "eval_bytecode")


def cache_dir() -> Path:
    given = os.environ.get("MERMAIDX_CACHE_DIR")
    if given:
        return Path(given)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "mermaidx" / "bytecode"


@lru_cache(maxsize=1)
def _engine_tag(ctx_type: type) -> str:
    """What a bytecode file must have been made by: the QuickJS binding's version and the bytecode version byte
    its compiler writes first (a different QuickJS refuses the file, so the file must never reach it)."""
    try:
        package = version("quickjs-ng")
    except Exception:
        package = "unknown"
    probe = ctx_type().compile("0")
    return f"quickjs-ng-{package}-bc{probe[0]}"


@lru_cache(maxsize=16)  # the same script object comes back for every context, so this hashes each source once
def _key(tag: str, source: str) -> str:
    digest = hashlib.sha256(tag.encode())
    digest.update(b"\0")
    digest.update(source.encode("utf-8", "surrogatepass"))
    return digest.hexdigest()[:40]


def _file(name: str, key: str) -> Path:
    return cache_dir() / f"{name}-{key}.qbc"


def _read(path: Path) -> bytes | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    head = len(_MAGIC) + _HASH_BYTES
    if len(raw) <= head or not raw.startswith(_MAGIC):
        return None
    payload = raw[head:]
    if hashlib.sha256(payload).digest() != raw[len(_MAGIC):head]:
        return None
    return payload


def _write(name: str, path: Path, payload: bytes) -> None:
    """Best effort: a cache that cannot be written is only slower. Written beside the file and renamed into place,
    so another process never reads half of it; the files of older sources of the same script are removed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        temporary.write_bytes(_MAGIC + hashlib.sha256(payload).digest() + payload)
        os.replace(temporary, path)
        for old in path.parent.glob(f"{name}-*.qbc"):
            if old != path:
                old.unlink(missing_ok=True)
    except OSError:
        pass


def bytecode_for(ctx, source: str, name: str) -> bytes | None:
    """The bytecode of `source`, from memory, from the cache directory, or compiled now with `ctx`; None when it
    cannot be had (then the caller evaluates the source)."""
    key = _key(_engine_tag(type(ctx)), source)
    with _lock:
        if key in _memory:
            return _memory[key]
        path = _file(name, key)
        payload = _read(path)
        if payload is None:
            try:
                payload = ctx.compile(source, name)
            except Exception:  # a script that does not compile fails the same way when evaluated
                payload = None
            if payload is not None:
                _write(name, path, payload)
        _memory[key] = payload
        return payload


def run(ctx, source: str, name: str = "<input>"):
    """`ctx.eval(source)`, through bytecode when that is available and worth it. An exception raised by the script
    itself is the script's, as with `eval`: the bytecode is never run unless it was made by this QuickJS."""
    if len(source) >= MIN_SOURCE_CHARS and enabled() and supported(ctx):
        payload = bytecode_for(ctx, source, name)
        if payload is not None:
            return ctx.eval_bytecode(payload)
    return ctx.eval(source)
