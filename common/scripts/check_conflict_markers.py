#!/usr/bin/env python3
"""Refuse trees that still contain unresolved git conflict markers (FR #1634).

Scans text files for lines starting with the standard conflict markers::

    <<<<<<<
    =======
    >>>>>>>

Exit 0 when clean; exit 1 and print paths:line when any hit is found.
Used by CI and as the CAST IRON pre-merge gate for MRB seats.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Line-start markers (optional space after <<<<<<< / >>>>>>> per git).
MARKER_PREFIXES = ("<<<<<<<", "=======", ">>>>>>>")

SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
}

# Binary / generated extensions we never treat as source.
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".7z",
    ".exe",
    ".dll",
    ".pyd",
    ".so",
    ".dylib",
    ".whl",
    ".msi",
    ".pyc",
    ".pyo",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp4",
    ".mp3",
    ".wav",
}


def _is_skipped_path(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return False


def line_has_conflict_marker(line: str) -> bool:
    s = line.lstrip("\ufeff")  # strip BOM if present
    # Exact git conflict open/sep/close (allow trailing label after marker).
    if s.startswith("<<<<<<< ") or s.startswith("<<<<<<<\t") or s.rstrip("\r\n") == "<<<<<<<":
        return True
    if s.startswith(">>>>>>> ") or s.startswith(">>>>>>>\t") or s.rstrip("\r\n") == ">>>>>>>":
        return True
    # Separator is exactly ======= (7 equals) optionally with CR; avoid matching
    # markdown/table underlines that are longer runs of '='.
    bare = s.rstrip("\r\n")
    if bare == "=======":
        return True
    return False


def scan_text(text: str) -> list[int]:
    """Return 1-based line numbers that look like conflict markers."""
    hits: list[int] = []
    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        if line_has_conflict_marker(line):
            hits.append(i)
    return hits


def scan_file(path: Path) -> list[tuple[int, str]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    # Skip obvious binary (NUL in first 8 KiB).
    sample = raw[:8192]
    if b"\x00" in sample:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return []
    out: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        if line_has_conflict_marker(line):
            out.append((i, line.rstrip("\r\n")[:120]))
    return out


def iter_files(root: Path, paths: list[Path] | None) -> list[Path]:
    if paths:
        files: list[Path] = []
        for p in paths:
            pp = p if p.is_absolute() else (root / p)
            if pp.is_file() and not _is_skipped_path(pp.relative_to(root) if pp.is_relative_to(root) else pp):
                files.append(pp)
            elif pp.is_dir():
                for f in pp.rglob("*"):
                    if f.is_file() and not _is_skipped_path(f.relative_to(root) if root in f.parents or f == root else f):
                        files.append(f)
        return files
    files = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        if _is_skipped_path(rel):
            continue
        files.append(f)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fail if unresolved git conflict markers are present (FR #1634).")
    ap.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional files/dirs to scan (default: repo root).",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root for relative paths (default: cwd).",
    )
    args = ap.parse_args(argv)
    root = (args.root or Path.cwd()).resolve()
    files = iter_files(root, list(args.paths) if args.paths else None)
    bad: list[str] = []
    for f in files:
        hits = scan_file(f)
        if not hits:
            continue
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        for lineno, snippet in hits:
            bad.append(f"{rel}:{lineno}: {snippet}")
    if bad:
        print("check_conflict_markers: FAIL — unresolved conflict markers:", file=sys.stderr)
        for line in bad[:200]:
            print(f"  {line}", file=sys.stderr)
        if len(bad) > 200:
            print(f"  ... and {len(bad) - 200} more", file=sys.stderr)
        return 1
    print("check_conflict_markers: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
