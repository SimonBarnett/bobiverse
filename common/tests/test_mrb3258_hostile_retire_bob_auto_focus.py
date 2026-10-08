# -*- coding: utf-8 -*-
"""MRB #3258 hostile gates for FR #3190 BobAutoFocus retirement.

Pins after product PR #3258:
- jeeves post-upgrade task list is exactly BobCallback + BobAutoFeed
- Unregister-BobAutoFocus.ps1 disables/unregisters and renames ops artifacts
- no Register/Start of BobAutoFocus in Update-BobiverseService
- monitor auto_focus.py is read-only (no focus write / PRIVMSG)
- docs/skills require repo-level !focus only
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_layout import ROOT

UPD = ROOT / "common" / "scripts" / "Update-BobiverseService.ps1"
RETIRE = ROOT / "common" / "scripts" / "Unregister-BobAutoFocus.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
FLEET = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"
JEEVES = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"
MONITOR = ROOT / "jeeves" / "tools" / "monitor" / "auto_focus.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb3258_post_upgrade_task_list_exact():
    t = _read(UPD)
    m = re.search(r"foreach\s*\(\s*\$tn\s+in\s+@\(([^)]+)\)\s*\)", t, re.I)
    assert m
    names = [x.strip().strip("'\"") for x in m.group(1).split(",")]
    assert names == ["BobCallback", "BobAutoFeed"]
    assert "Unregister-BobAutoFocus.ps1" in t
    assert "post-upgrade-bobautofocus-retired" in t
    assert not re.search(r"Start-ScheduledTask[^\n]*BobAutoFocus", t)
    assert not re.search(r"Register-ScheduledTask[^\n]*BobAutoFocus", t)


def test_mrb3258_unregister_renames_ops_artifacts(tmp_path: Path):
    ops = tmp_path / "ops"
    ops.mkdir()
    (ops / "auto-focus.py").write_text("# spam\n", encoding="utf-8")
    (ops / "BobAutoFocus.xml").write_text("<Task/>\n", encoding="utf-8")
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RETIRE),
            "-OpsRoot",
            str(ops),
            "-Quiet",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert not (ops / "auto-focus.py").exists()
    assert not (ops / "BobAutoFocus.xml").exists()
    retired = list(ops.glob("auto-focus.py.retired-fr3190-*"))
    assert retired, "ops auto-focus.py should be renamed aside"
    assert list(ops.glob("BobAutoFocus.xml.retired-fr3190-*"))


def test_mrb3258_monitor_read_only_no_focus_write():
    t = _read(MONITOR)
    assert "FR #3190" in t
    assert "never writes" in t.lower() or "read-only" in t.lower() or "NOT the retired" in t
    body = re.sub(r'""".*?"""', "", t, count=1, flags=re.S)
    assert "write_text" not in body
    assert "PRIVMSG" not in body
    assert "!focus" not in body


def test_mrb3258_docs_repo_level_focus_only():
    blob = _read(POST) + "\n" + _read(FLEET) + "\n" + _read(JEEVES)
    assert "FR #3190" in blob
    assert "BobAutoFocus" in blob
    assert "repo-level" in blob.lower() and "!focus" in blob
    assert re.search(r"retir|unregister", blob, re.I)
