"""FR #7910: scripts bob-worker launches by path must ship beside the frozen exe.

``_resolve_installed_worker_script`` skips the PyInstaller ``_MEI`` extract.
A worker-only artifact that is only ``bob-worker.exe`` therefore leaves
``opencode_tool_wedge.py`` and ``opencode_turn_guard.py`` missing on the box.
The build bundles those files as ``worker-scripts`` data and also copies them
into the CI artifact under ``scripts\\``. On a frozen start the worker writes
the bundle out to ``<exe dir>\\scripts``, which the resolver already searches.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BUNDLE_DIR_NAME = "worker-scripts"
_NAME_RX = re.compile(
    r"""_resolve_installed_worker_script\(\s*["']([A-Za-z0-9_]+\.py)["']"""
)


def by_path_script_names(bob_worker_text: str) -> list[str]:
    """Names passed as the first argument of ``_resolve_installed_worker_script``."""
    return sorted(set(_NAME_RX.findall(bob_worker_text or "")))


def copy_by_path_scripts(bob_worker: Path, source_dir: Path, dest: Path) -> list[str]:
    """Copy each by-path script into ``dest``. Raise if any source file is absent."""
    text = Path(bob_worker).read_text(encoding="utf-8")
    names = by_path_script_names(text)
    if not names:
        raise SystemExit("no by-path worker scripts found in %s" % bob_worker)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for name in names:
        src = Path(source_dir) / name
        if not src.is_file():
            missing.append(name)
            continue
        (dest / name).write_bytes(src.read_bytes())
    if missing:
        raise SystemExit("by-path worker scripts missing from %s: %s" % (source_dir, ", ".join(missing)))
    return names


def check_by_path_scripts(bob_worker: Path, dest: Path) -> list[str]:
    """Fail when ``dest`` does not contain every by-path script."""
    text = Path(bob_worker).read_text(encoding="utf-8")
    names = by_path_script_names(text)
    if not names:
        raise SystemExit("no by-path worker scripts found in %s" % bob_worker)
    missing = [name for name in names if not (Path(dest) / name).is_file()]
    if missing:
        raise SystemExit("bob-worker artifact missing by-path scripts: %s" % ", ".join(missing))
    return names


def extract_bundled_scripts() -> list[str]:
    """Frozen exe: write bundled scripts next to the exe. No-op from source."""
    if not getattr(sys, "frozen", False):
        return []
    root = Path(getattr(sys, "_MEIPASS", "") or "")
    src = root / BUNDLE_DIR_NAME
    if not src.is_dir():
        return []
    dest = Path(sys.executable).resolve().parent / "scripts"
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    written: list[str] = []
    for path in sorted(src.glob("*.py")):
        target = dest / path.name
        try:
            data = path.read_bytes()
            if target.is_file() and target.read_bytes() == data:
                written.append(path.name)
                continue
            target.write_bytes(data)
            written.append(path.name)
        except OSError:
            continue
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #7910 ship worker by-path scripts")
    p.add_argument("--bob-worker", required=True)
    p.add_argument("--list", action="store_true")
    p.add_argument("--copy", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--source-dir", default="")
    p.add_argument("--dest", default="")
    args = p.parse_args(argv)
    bob_worker = Path(args.bob_worker)
    if args.list:
        text = bob_worker.read_text(encoding="utf-8")
        for name in by_path_script_names(text):
            print(name)
        return 0
    if args.copy:
        copy_by_path_scripts(bob_worker, Path(args.source_dir), Path(args.dest))
        return 0
    if args.check:
        check_by_path_scripts(bob_worker, Path(args.dest))
        return 0
    p.error("pass --list, --copy, or --check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
