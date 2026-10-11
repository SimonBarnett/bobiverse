"""FR #4094: airc_console must define ConsoleSession / Manager / HandleResult once each."""
from __future__ import annotations

import ast
from pathlib import Path

from repo_layout import ROOT


def _airc_console_path() -> Path:
    return ROOT / "airc" / "scripts" / "airc_console.py"


def _toplevel_class_counts(path: Path) -> dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    counts: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            counts[node.name] = counts.get(node.name, 0) + 1
    return counts


def test_fr4094_console_session_classes_defined_once():
    counts = _toplevel_class_counts(_airc_console_path())
    for name in ("ConsoleSession", "ConsoleSessionManager", "HandleResult"):
        assert counts.get(name) == 1, f"{name} defined {counts.get(name)} times (want 1)"


def test_fr4094_handle_result_keeps_auth_allow_fields():
    """Surviving HandleResult must keep FR #4067 allow_* fields (no accidental drop)."""
    import sys

    scripts = str(ROOT / "airc" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import airc_console as ac

    hr = ac.HandleResult(
        action="shell",
        allow_mode="+o",
        allow_account="simon",
        allow_channel="#ionos",
    )
    assert hr.allow_mode == "+o"
    assert hr.allow_account == "simon"
    assert hr.allow_channel == "#ionos"
    assert "deny_reason" in ac.HandleResult.__dataclass_fields__
