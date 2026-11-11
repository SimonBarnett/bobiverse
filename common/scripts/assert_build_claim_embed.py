#!/usr/bin/env python3
"""FR #6558 / #6576: assert a built bob-ear/jeeves tree embeds build-route claim code.

Looks for ``PYZ-00.pyz`` under a build work dir (or a one-file ``.exe`` via
PyInstaller ``CArchiveReader``), extracts the frozen ``bobiverse_build`` code
object, and checks structural pins for claim expiry / reclaim / logging:

* ``_claim_build_route_marker_detail`` exists
* ``claim_build_route_marker`` accepts ``stale_after_s``
* ``consume_build_v1`` accepts ``stale_claim_s`` and ``log``
* module carries the ``.reclaim.lock`` constant

Exit 0 on pass, 1 on fail, 2 when no archive is present and --allow-missing.

Marshal bytecode is Python-version specific: run this helper with the same
Python (3.12) used to freeze the executable.
"""

from __future__ import annotations

import argparse
import hashlib
import marshal
import sys
import types
from pathlib import Path

MODULE = "bobiverse_build"
DETAIL = "_claim_build_route_marker_detail"
CLAIM = "claim_build_route_marker"
CONSUME = "consume_build_v1"
RECLAIM_LOCK = ".reclaim.lock"


def find_pyz(root: Path) -> Path | None:
    hits = sorted(root.rglob("PYZ-00.pyz"))
    return hits[0] if hits else None


def iter_code(co: types.CodeType):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from iter_code(c)


def find_func(module_code: types.CodeType, name: str) -> types.CodeType | None:
    for co in iter_code(module_code):
        if co.co_name == name:
            return co
    return None


def _zlib_reader():
    try:
        from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader

        return ZlibArchiveReader
    except Exception:
        from PyInstaller.archive.readers import ZlibArchiveReader  # type: ignore

        return ZlibArchiveReader


def problems_in_module_code(module_code: types.CodeType) -> list[str]:
    """Return reasons the frozen bobiverse_build lacks FR #6558 pins ([] = OK)."""
    out: list[str] = []
    detail = find_func(module_code, DETAIL)
    if detail is None:
        out.append(f"function {DETAIL} not found")
    claim = find_func(module_code, CLAIM)
    if claim is None:
        out.append(f"function {CLAIM} not found")
    else:
        names = set(claim.co_varnames) | set(getattr(claim, "co_freevars", ()))
        # Keyword-only params land in co_varnames after positional.
        if "stale_after_s" not in claim.co_varnames:
            out.append(f"{CLAIM} missing parameter stale_after_s")
    consume = find_func(module_code, CONSUME)
    if consume is None:
        out.append(f"function {CONSUME} not found")
    else:
        if "stale_claim_s" not in consume.co_varnames:
            out.append(f"{CONSUME} missing parameter stale_claim_s")
        if "log" not in consume.co_varnames:
            out.append(f"{CONSUME} missing parameter log")
    consts = [c for c in module_code.co_consts if isinstance(c, str)]
    # Nested function consts also carry the lock name.
    for co in iter_code(module_code):
        consts.extend(c for c in co.co_consts if isinstance(c, str))
    if RECLAIM_LOCK not in consts:
        out.append(f"module missing {RECLAIM_LOCK!r} constant")
    return out


def _fail(msg: str) -> None:
    raise SystemExit(f"FR #6558: {msg}")


def read_pyz_module(pyz: Path, name: str = MODULE) -> types.CodeType:
    try:
        ZlibArchiveReader = _zlib_reader()
    except Exception as exc:  # pragma: no cover - build box always has PyInstaller
        _fail(f"PyInstaller not importable to read {pyz}: {exc}")
    arch = ZlibArchiveReader(str(pyz))
    toc = getattr(arch, "toc", None) or getattr(arch, "_toc", None) or {}
    keys = set(toc.keys()) if isinstance(toc, dict) else {str(x) for x in toc}
    if name not in keys and not any(str(k) == name or str(k).startswith(name + ".") for k in keys):
        _fail(f"no {name} module in {pyz} (hidden-import missing?)")
    co = arch.extract(name)
    if isinstance(co, (bytes, bytearray)):
        co = marshal.loads(co)
    if not isinstance(co, types.CodeType):
        _fail(f"{name} in {pyz} is not a code object ({type(co).__name__})")
    return co


def read_exe_module(exe: Path, name: str = MODULE) -> types.CodeType:
    """Extract ``bobiverse_build`` from a one-file frozen executable."""
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except Exception as exc:  # pragma: no cover
        _fail(f"PyInstaller CArchiveReader not importable for {exe}: {exc}")
    try:
        from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader
    except Exception:
        from PyInstaller.archive.readers import ZlibArchiveReader  # type: ignore

    archive = CArchiveReader(str(exe))
    # Prefer open_embedded_archive when present (PyInstaller 5/6).
    pyz_data = None
    opener = getattr(archive, "open_embedded_archive", None)
    if callable(opener):
        try:
            pyz_data = opener("PYZ-00.pyz")
        except Exception:
            pyz_data = None
    if pyz_data is None:
        # Fall back: find PYZ entry and extract raw bytes.
        toc = getattr(archive, "toc", None) or getattr(archive, "_toc", None) or []
        entries = toc.items() if isinstance(toc, dict) else toc
        raw = None
        for item in entries:
            if isinstance(item, tuple) and len(item) >= 1:
                key = item[0] if not isinstance(toc, dict) else item
            else:
                key = item
            label = key if isinstance(key, str) else (item[0] if isinstance(item, tuple) else str(item))
            if "PYZ-00" in str(label):
                try:
                    raw = archive.extract(label) if hasattr(archive, "extract") else None
                except Exception:
                    raw = None
                break
        if raw is None:
            _fail(f"no PYZ-00.pyz inside {exe}")
        tmp = exe.with_suffix(".pyz.extract")
        try:
            if isinstance(raw, tuple):
                raw = raw[0] if raw else b""
            tmp.write_bytes(raw if isinstance(raw, (bytes, bytearray)) else bytes(raw))
            return read_pyz_module(tmp, name)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    # open_embedded_archive returned a reader or path-like
    if hasattr(pyz_data, "extract"):
        co = pyz_data.extract(name)
        if isinstance(co, (bytes, bytearray)):
            co = marshal.loads(co)
        if not isinstance(co, types.CodeType):
            _fail(f"{name} in {exe} PYZ is not a code object ({type(co).__name__})")
        return co
    _fail(f"could not open embedded PYZ from {exe}")


def check_module_code(co: types.CodeType, where: str) -> None:
    probs = problems_in_module_code(co)
    if probs:
        _fail(f"embedded bobiverse_build in {where} stale: " + "; ".join(probs))
    print(f"OK FR #6558: {where} embeds bobiverse_build claim expiry/logging")


def check_pyz(pyz: Path) -> None:
    check_module_code(read_pyz_module(pyz), str(pyz))


def check_pyc_file(path: Path) -> None:
    data = path.read_bytes()
    check_module_code(marshal.loads(data[16:]), str(path))


def _print_fingerprint(path: Path) -> None:
    if path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"sha256={digest} path={path}")
    print(f"python={sys.version.split()[0]}")
    try:
        import PyInstaller

        print(f"pyinstaller={PyInstaller.__version__}")
    except Exception:
        print("pyinstaller=missing")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "root",
        type=Path,
        help="Build work dir (contains PYZ-00.pyz), a bobiverse_build.pyc, or a one-file .exe",
    )
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Exit 2 (not 1) when no PYZ/module is found",
    )
    args = p.parse_args(argv)
    root = args.root
    if not root.exists():
        if args.allow_missing:
            print(f"FR #6558: missing path {root} (allow-missing)", file=sys.stderr)
            return 2
        print(f"FR #6558: path not found: {root}", file=sys.stderr)
        return 1
    _print_fingerprint(root if root.is_file() else root)
    if root.is_file():
        if root.suffix.lower() == ".exe":
            check_module_code(read_exe_module(root), str(root))
            return 0
        check_pyc_file(root)
        return 0
    pyz = find_pyz(root)
    if pyz is None:
        loose = sorted(root.rglob("bobiverse_build*.pyc"))
        if loose:
            check_pyc_file(loose[0])
            return 0
        msg = f"FR #6558: no PYZ-00.pyz under {root}"
        if args.allow_missing:
            print(msg + " (allow-missing)", file=sys.stderr)
            return 2
        print(msg, file=sys.stderr)
        return 1
    check_pyz(pyz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
