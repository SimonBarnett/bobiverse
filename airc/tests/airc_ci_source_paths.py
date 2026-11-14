"""Shared airc CI path-filter allowlist (FR #7276)."""
from __future__ import annotations

import ast
from pathlib import Path

from repo_layout import ROOT

SCRIPTS_COMMON = ROOT / "common" / "scripts"
SCRIPTS_AIRC = ROOT / "airc" / "scripts"
ENTRY = SCRIPTS_AIRC / "airc_console_service.py"

# Hidden imports Build-Airc.ps1 always freezes (dynamic imports not visible to AST).
AIRC_HIDDEN_IMPORTS = (
    "account_map",
    "airc_console",
    "airc_jobs",
    "airc_dcc_bulk",
    "airc_credman",
    "airc_cred_irc",
    "airc_passed_cred",
    "airc_isolated",
    "airc_fail_intake",
    "crash_report",
    "airc_seal_file",
    "seal",
    "filexfer",
    "protect",
    "wire",
)

AIRC_CI_STATIC_PATHS = [
    ".github/workflows/build-airc.yml",
    "airc/**",
    "airc/scripts/Build-Airc.ps1",
    "airc/tests/airc_ci_source_paths.py",
    "airc/tests/test_fr7276_airc_build_ci.py",
    "common/scripts/Bobiverse-Common.ps1",
    "common/requirements-freeze.txt",
]


def _module_file(name: str) -> Path | None:
    if not name or name.startswith("."):
        return None
    top = name.split(".", 1)[0]
    for base in (SCRIPTS_AIRC, SCRIPTS_COMMON):
        cand = base / (top + ".py")
        if cand.is_file():
            return cand
    return None


def frozen_airc_common_script_paths(entry: Path = ENTRY) -> list[str]:
    """``common/scripts/*.py`` modules reachable from airc_console_service (+ Build-Airc hidden)."""
    seen: set[Path] = set()
    stack: list[Path] = [entry.resolve()]
    for name in AIRC_HIDDEN_IMPORTS:
        found = _module_file(name)
        if found is not None:
            stack.append(found.resolve())
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
                resolved.relative_to(SCRIPTS_COMMON.resolve())
            except ValueError:
                try:
                    resolved.relative_to(SCRIPTS_AIRC.resolve())
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


def airc_ci_source_paths() -> list[str]:
    """Full workflow path-filter list: static pins plus frozen common scripts."""
    return sorted(set(AIRC_CI_STATIC_PATHS) | set(frozen_airc_common_script_paths()))