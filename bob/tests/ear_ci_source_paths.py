"""Shared ear CI path-filter allowlist (FR #7179 / #7202)."""
from __future__ import annotations

import ast
from pathlib import Path

from repo_layout import ROOT

SCRIPTS = ROOT / "common" / "scripts"
IRC_AGENT = SCRIPTS / "irc_agent.py"

# Non-Python / wrapper / test pins that also rebuild the ear.
EAR_CI_STATIC_PATHS = [
    ".github/workflows/build-bob-ear.yml",
    "bob/scripts/Build-BobEar.ps1",
    "bob/scripts/Install-BobEarExe.ps1",
    "bob/docs/deploy-pool-monitor-manifest.txt",
    "bob/tests/test_fr6254_ear_build_provenance_align.py",
    "bob/tests/test_fr7179_ear_tray_ci_main_push.py",
    "bob/tests/test_fr7202_ear_ci_frozen_imports.py",
    "bob/tests/ear_ci_source_paths.py",
]


def _module_file(name: str) -> Path | None:
    if not name or name.startswith("."):
        return None
    top = name.split(".", 1)[0]
    cand = SCRIPTS / (top + ".py")
    if cand.is_file():
        return cand
    pkg = SCRIPTS / top / "__init__.py"
    if pkg.is_file():
        return pkg
    return None


def frozen_common_script_paths(entry: Path = IRC_AGENT) -> list[str]:
    """``common/scripts/*.py`` modules reachable from irc_agent (PyInstaller freeze)."""
    seen: set[Path] = set()
    stack = [entry.resolve()]
    while stack:
        path = stack.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        for name in names:
            found = _module_file(name)
            if found is None:
                continue
            resolved = found.resolve()
            try:
                resolved.relative_to(SCRIPTS.resolve())
            except ValueError:
                continue
            if resolved not in seen:
                stack.append(resolved)
    rels = []
    for p in seen:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("common/scripts/"):
            rels.append(rel)
    return sorted(set(rels))


def ear_ci_source_paths() -> list[str]:
    """Full workflow path-filter list: static pins plus frozen common scripts."""
    return sorted(set(EAR_CI_STATIC_PATHS) | set(frozen_common_script_paths()))
