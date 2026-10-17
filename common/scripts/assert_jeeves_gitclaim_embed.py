#!/usr/bin/env python3
"""FR #4608: assert a built jeeves PyInstaller tree embeds MRB exact-seat gitclaim.

Looks for ``PYZ-00.pyz`` (or a direct ``gitclaim*.pyc``) under a build work dir,
then requires the embedded module bytes to contain the FR #2604 / #4606 markers
(``if task == \"MRB\":`` continues before ``nick_inherits_dead_seat``).

Exit 0 on pass, 1 on fail, 2 when no archive is present (caller may skip).
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

# Contiguous markers that must appear in the frozen gitclaim module (FR #4608).
MARKERS = (
    b"FR #2604 / #4606",
    b'if task == "MRB":',
    b"nick_inherits_dead_seat",
)


def find_pyz(root: Path) -> Path | None:
    hits = sorted(root.rglob("PYZ-00.pyz"))
    return hits[0] if hits else None


def find_gitclaim_member(zf: zipfile.ZipFile) -> str | None:
    names = zf.namelist()
    for n in names:
        base = n.replace("\\", "/").rsplit("/", 1)[-1]
        if base.startswith("gitclaim") and (
            base.endswith(".pyc") or base.endswith(".py")
        ):
            return n
    return None


def assert_bytes_have_markers(blob: bytes) -> list[str]:
    missing = []
    for m in MARKERS:
        if m not in blob:
            missing.append(m.decode("ascii", errors="replace"))
    return missing


def check_pyz(pyz: Path) -> None:
    with zipfile.ZipFile(pyz, "r") as zf:
        member = find_gitclaim_member(zf)
        if not member:
            raise SystemExit(
                f"FR #4608: no gitclaim module in {pyz} (hidden-import missing?)"
            )
        blob = zf.read(member)
    missing = assert_bytes_have_markers(blob)
    if missing:
        raise SystemExit(
            "FR #4608: embedded gitclaim missing markers: "
            + ", ".join(missing)
        )
    print(f"OK FR #4608: {pyz} embeds gitclaim with MRB exact-seat markers")


def check_pyc_file(path: Path) -> None:
    blob = path.read_bytes()
    missing = assert_bytes_have_markers(blob)
    if missing:
        raise SystemExit(
            f"FR #4608: {path} missing markers: " + ", ".join(missing)
        )
    print(f"OK FR #4608: {path} has MRB exact-seat markers")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "root",
        type=Path,
        help="Build work dir (contains PYZ-00.pyz) or a gitclaim.pyc path",
    )
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Exit 2 (not 1) when no PYZ/gitclaim is found",
    )
    args = p.parse_args(argv)
    root = args.root
    if not root.exists():
        if args.allow_missing:
            print(f"FR #4608: missing path {root} (allow-missing)", file=sys.stderr)
            return 2
        print(f"FR #4608: path not found: {root}", file=sys.stderr)
        return 1

    if root.is_file():
        check_pyc_file(root)
        return 0

    pyz = find_pyz(root)
    if pyz is None:
        # Fallback: loose pyc under work dir
        loose = sorted(root.rglob("gitclaim*.pyc"))
        if loose:
            check_pyc_file(loose[0])
            return 0
        msg = f"FR #4608: no PYZ-00.pyz under {root}"
        if args.allow_missing:
            print(msg + " (allow-missing)", file=sys.stderr)
            return 2
        print(msg, file=sys.stderr)
        return 1

    check_pyz(pyz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
