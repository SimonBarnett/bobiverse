#!/usr/bin/env python3
"""FR #6487: assert a built jeeves/bob-ear PyInstaller tree embeds PyYAML.

Looks for ``PYZ-00.pyz`` under a build work dir and checks that ``yaml`` (and
preferably ``_yaml``) is present in the archive TOC. Exit 0 on pass, 1 on fail,
2 when no archive is present and --allow-missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def find_pyz(root: Path) -> Path | None:
    hits = sorted(root.rglob("PYZ-00.pyz"))
    return hits[0] if hits else None


def toc_names(pyz: Path) -> set[str]:
    try:
        from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader
    except Exception:
        from PyInstaller.archive.readers import ZlibArchiveReader  # type: ignore
    arch = ZlibArchiveReader(str(pyz))
    raw = getattr(arch, "toc", None) or getattr(arch, "_toc", None) or {}
    if isinstance(raw, dict):
        return {str(k) for k in raw.keys()}
    return {str(x) for x in raw}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path, help="PyInstaller work/dist parent dir")
    p.add_argument("--allow-missing", action="store_true")
    args = p.parse_args(argv)
    pyz = find_pyz(args.work)
    if pyz is None:
        print("FR #6487: no PYZ-00.pyz under", args.work)
        return 2 if args.allow_missing else 1
    names = toc_names(pyz)
    need = {"yaml"}
    missing = sorted(n for n in need if n not in names and not any(
        x == n or x.startswith(n + ".") for x in names
    ))
    if missing:
        sample = ", ".join(sorted(names)[:12])
        print(f"FR #6487: PYZ missing {missing}; sample toc={sample}")
        return 1
    print(f"FR #6487: yaml present in {pyz}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
