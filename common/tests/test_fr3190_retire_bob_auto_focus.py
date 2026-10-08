"""FR #3190: retire BobAutoFocus (ops auto-focus.py per-item !focus spam).

Acceptance that fails on pre-3190 main:
- Update-BobiverseService jeeves post-upgrade must not Start-ScheduledTask BobAutoFocus
- A retire/unregister script exists and targets BobAutoFocus + ops auto-focus.py
- Docs/skills say BobAutoFocus is retired (repo-level !focus only)
"""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
RETIRE = ROOT / "common" / "scripts" / "Unregister-BobAutoFocus.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
JEEVES_SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"
FLEET = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
MONITOR_AF = ROOT / "jeeves" / "tools" / "monitor" / "auto_focus.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr3190_update_service_does_not_restart_bob_auto_focus():
    t = _read(UPD)
    # Find the post-upgrade scheduled-task restart foreach (FR #1018 / FR #3190).
    m = re.search(
        r"foreach\s*\(\s*\$tn\s+in\s+@\(([^)]+)\)\s*\)",
        t,
        re.I,
    )
    assert m, "jeeves post-upgrade foreach task list missing"
    task_list = m.group(1)
    assert "BobCallback" in task_list
    assert "BobAutoFeed" in task_list
    assert "BobAutoFocus" not in task_list
    # Never Start-ScheduledTask BobAutoFocus; leftover task is retired instead.
    assert not re.search(r"Start-ScheduledTask[^\n]*BobAutoFocus", t)
    assert "'BobAutoFocus'" not in t and '"BobAutoFocus"' not in t
    assert "Unregister-BobAutoFocus.ps1" in t
    assert "post-upgrade-bobautofocus-retired" in t


def test_fr3190_unregister_script_exists_and_retires():
    assert RETIRE.is_file(), "Unregister-BobAutoFocus.ps1 missing"
    t = _read(RETIRE)
    assert "FR #3190" in t
    assert "BobAutoFocus" in t
    assert "Unregister-ScheduledTask" in t or "Disable-ScheduledTask" in t
    assert "auto-focus.py" in t
    assert "WhatIf" in t or "DryRun" in t or "$WhatIf" in t


def test_fr3190_docs_or_skill_say_retired():
    blob = ""
    for p in (POST, JEEVES_SKILL, FLEET):
        if p.is_file():
            blob += _read(p) + "\n"
    assert "FR #3190" in blob or "BobAutoFocus" in blob
    assert re.search(r"retir|unregister|do not re-?enable|repo-level !focus", blob, re.I)


def test_fr3190_monitor_auto_focus_is_not_ops_spammer():
    """jeeves tools/monitor/auto_focus.py is a health check, not the retired ops task."""
    t = _read(MONITOR_AF)
    assert "BobAutoFocus" not in t or "retir" in t.lower() or "not the" in t.lower()
    # Must not emit !focus / PRIVMSG (docstring may mention them as forbidden).
    body = re.sub(r'""".*?"""', "", t, count=1, flags=re.S)
    body = re.sub(r"'''.*?'''", "", body, count=1, flags=re.S)
    assert "PRIVMSG" not in body
    assert "!focus" not in body
    assert "append" not in body.lower() or "retir" in t.lower()
