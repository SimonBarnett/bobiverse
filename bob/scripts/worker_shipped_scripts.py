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
# FR #7991: a by-path script may import a sibling ``.py`` from the same scripts
# dir (``skill_dag_mcp`` -> ``skill_dag_index``). Ship those modules too, or the
# MCP host gets ``ModuleNotFoundError`` while the CLI works from the repo.
_LOCAL_IMPORT_RX = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import|import\s+([A-Za-z_][A-Za-z0-9_]*))",
    re.MULTILINE,
)


def by_path_script_names(bob_worker_text: str) -> list[str]:
    """Names passed as the first argument of ``_resolve_installed_worker_script``."""
    return sorted(set(_NAME_RX.findall(bob_worker_text or "")))


def local_script_imports(script: Path) -> list[str]:
    """Sibling ``*.py`` module names imported by ``script`` (FR #7991)."""
    try:
        text = Path(script).read_text(encoding="utf-8")
    except OSError:
        return []
    names: set[str] = set()
    for m in _LOCAL_IMPORT_RX.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip()
        if name:
            names.add(name)
    return sorted(names)


def shipped_script_names(
    bob_worker: Path,
    source_dir: Path,
    *,
    direct_names: list[str] | None = None,
) -> list[str]:
    """By-path scripts plus their transitive sibling modules (FR #7991)."""
    if direct_names is None:
        text = Path(bob_worker).read_text(encoding="utf-8")
        direct_names = by_path_script_names(text)
    source = Path(source_dir)
    out: list[str] = []
    seen: set[str] = set()
    queue: list[str] = list(direct_names)
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
        for mod in local_script_imports(source / name):
            dep = mod + ".py"
            if dep not in seen and (source / dep).is_file():
                queue.append(dep)
    return sorted(out)


def copy_by_path_scripts(bob_worker: Path, source_dir: Path, dest: Path) -> list[str]:
    """Copy each by-path script (and its sibling modules) into ``dest``.

    Raise if any required source file is absent.
    """
    text = Path(bob_worker).read_text(encoding="utf-8")
    direct = by_path_script_names(text)
    if not direct:
        raise SystemExit("no by-path worker scripts found in %s" % bob_worker)
    names = shipped_script_names(bob_worker, source_dir, direct_names=direct)
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


def check_by_path_scripts(bob_worker: Path, dest: Path, *, source_dir: Path | None = None) -> list[str]:
    """Fail when ``dest`` does not contain every by-path script and sibling module."""
    text = Path(bob_worker).read_text(encoding="utf-8")
    direct = by_path_script_names(text)
    if not direct:
        raise SystemExit("no by-path worker scripts found in %s" % bob_worker)
    names = list(direct)
    if source_dir is not None:
        names = shipped_script_names(bob_worker, source_dir, direct_names=direct)
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
    source_dir = Path(args.source_dir) if args.source_dir else bob_worker.parent
    if args.list:
        for name in shipped_script_names(bob_worker, source_dir):
            print(name)
        return 0
    if args.copy:
        copy_by_path_scripts(bob_worker, source_dir, Path(args.dest))
        return 0
    if args.check:
        check_by_path_scripts(bob_worker, Path(args.dest), source_dir=source_dir)
        return 0
    p.error("pass --list, --copy, or --check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
