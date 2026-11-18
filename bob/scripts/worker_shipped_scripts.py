"""FR #7910 / #8202: scripts bob-worker launches by path must ship beside the frozen exe.

``_resolve_installed_worker_script`` skips the PyInstaller ``_MEI`` extract.
A worker-only artifact that is only ``bob-worker.exe`` therefore leaves
``opencode_tool_wedge.py`` and ``opencode_turn_guard.py`` missing on the box.
The build bundles those files as ``worker-scripts`` data and also copies them
into the CI artifact under ``scripts\\``. On a frozen start the worker writes
the bundle out to ``<exe dir>\\scripts``, which the resolver already searches.

FR #8202: the frozen worker prefers those shipped copies (hash-checked against
the PyInstaller ``worker-scripts`` bundle) over a stale flat
``C:\\ai\\bob\\scripts`` tree. Set ``BOB_WORKER_USE_FLAT_SCRIPTS=1`` only for
explicit local/dev overrides. Unpack mismatches are overwritten; failures are
returned so startup can log them instead of silently running stale files.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BUNDLE_DIR_NAME = "worker-scripts"
# FR #8202: allow flat install scripts\\ to win (dev only). Default off when frozen.
FLAT_OVERRIDE_ENV = "BOB_WORKER_USE_FLAT_SCRIPTS"
_NAME_RX = re.compile(
    r"""_resolve_installed_worker_script\(\s*["']([A-Za-z0-9_]+\.py)["']"""
)
# FR #8156: fleet .ps1 the frozen exe invokes by path (Clear + Common sibling).
# Must ship beside bob-worker.exe so a stale install-root scripts\ copy cannot
# break job-end cleanup with unknown switches such as -SkipSeatDisk.
EXTRA_FLEET_SCRIPTS = (
    "Clear-BobiverseJobWorktrees.ps1",
    "Bobiverse-Common.ps1",
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


def fleet_ps1_script_names() -> list[str]:
    """FR #8156: PowerShell scripts the worker invokes against install-root / ship dir."""
    return list(EXTRA_FLEET_SCRIPTS)


def module_search_dirs(source_dir: Path) -> list[Path]:
    """bob/scripts plus common/scripts when this is a repo checkout (FR #8131).

    Installed workers have no common/ tree. Modules such as crash_report.py
    must be copied flat into the dist scripts folder.
    """
    source = Path(source_dir)
    dirs = [source]
    common = source.parent.parent / "common" / "scripts"
    if common.is_dir() and common.resolve() != source.resolve():
        dirs.append(common)
    return dirs


def find_module_file(name: str, source_dir: Path) -> Path | None:
    """First ``name`` under the script dir or common/scripts."""
    for folder in module_search_dirs(source_dir):
        path = folder / name
        if path.is_file():
            return path
    return None


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
    # FR #8156: always include fleet .ps1 helpers the exe calls by path.
    direct_names = list(direct_names) + [
        n for n in fleet_ps1_script_names() if n not in direct_names
    ]
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
        found = find_module_file(name, source)
        if found is None:
            continue
        for mod in local_script_imports(found):
            dep = mod + ".py"
            if dep not in seen and find_module_file(dep, source) is not None:
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
        src = find_module_file(name, Path(source_dir))
        if src is None:
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


def use_flat_scripts_override(env: dict | None = None) -> bool:
    """True when ``BOB_WORKER_USE_FLAT_SCRIPTS`` requests flat install scripts (FR #8202)."""
    e = os.environ if env is None else env
    raw = str(e.get(FLAT_OVERRIDE_ENV) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def short_content_hash(data: bytes) -> str:
    """12-hex SHA-256 prefix for startup logs (no secrets)."""
    return hashlib.sha256(data).hexdigest()[:12]


@dataclass
class ExtractBundledResult:
    """Outcome of unpacking ``worker-scripts`` beside the frozen exe (FR #8202)."""

    written: list[str] = field(default_factory=list)
    overwritten: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)
    dest: str = ""


def bundled_scripts_src_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    root = Path(getattr(sys, "_MEIPASS", "") or "")
    src = root / BUNDLE_DIR_NAME
    return src if src.is_dir() else None


def ship_scripts_dir() -> Path | None:
    """``<exe dir>\\scripts`` when frozen; else None."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return Path(sys.executable).resolve().parent / "scripts"
    except Exception:
        return None


def extract_bundled_scripts_result() -> ExtractBundledResult:
    """Frozen exe: write/hash-check bundled scripts next to the exe (FR #8202).

    The PyInstaller ``worker-scripts`` tree is the build manifest: each dest
    file must match those bytes. Mismatches are overwritten; OSError is
    recorded in ``failed`` instead of silently keeping the stale file.
    """
    out = ExtractBundledResult()
    if not getattr(sys, "frozen", False):
        return out
    src = bundled_scripts_src_dir()
    if src is None:
        return out
    dest = ship_scripts_dir()
    if dest is None:
        return out
    out.dest = str(dest)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        out.failed.append(("*", type(e).__name__))
        return out
    # FR #8156: extract both Python helpers and fleet .ps1 (Clear / Common).
    paths = sorted(list(src.glob("*.py")) + list(src.glob("*.ps1")))
    for path in paths:
        name = path.name
        target = dest / name
        try:
            data = path.read_bytes()
        except OSError as e:
            out.failed.append((name, type(e).__name__))
            continue
        out.hashes[name] = short_content_hash(data)
        try:
            if target.is_file():
                existing = target.read_bytes()
                if existing == data:
                    out.unchanged.append(name)
                    out.written.append(name)
                    continue
                target.write_bytes(data)
                out.overwritten.append(name)
                out.written.append(name)
                continue
            target.write_bytes(data)
            out.written.append(name)
        except OSError as e:
            out.failed.append((name, type(e).__name__))
    return out


def extract_bundled_scripts() -> list[str]:
    """Frozen exe: write bundled scripts next to the exe. No-op from source.

    Returns the names successfully present after extract (unchanged or written).
    Prefer ``extract_bundled_scripts_result`` when callers need overwrite/fail detail.
    """
    return list(extract_bundled_scripts_result().written)


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
