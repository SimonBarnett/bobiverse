"""MRB #6955 hostile pins for FR #6953 maintenance skip off-chair."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

MAINT = ROOT / "common" / "scripts" / "jeeves_maintenance.py"
MAIN = ROOT / "common" / "scripts" / "jeeves_main.py"
START = ROOT / "jeeves" / "scripts" / "Start-JeevesMaintenance.ps1"
DOCS = ROOT / "jeeves" / "docs" / "jeeves-exe-self-heal.md"


def test_mrb6955_chair_gate_before_would_spawn():
    text = MAINT.read_text(encoding="utf-8")
    assert "is_configured_chair_host" in text
    assert "jeeves_chair_host" in text
    assert "not_chair_host" in text
    # Gate must run before dry-run would_spawn logging.
    chair_i = text.index("if not chair_ok:")
    would_i = text.index('MaintenanceResult("dry-run", "would_spawn"')
    assert chair_i < would_i
    main = MAIN.read_text(encoding="utf-8")
    assert 'mr.reason == "not_chair_host"' in main
    assert "exit_code = 0" in main[main.index("not_chair_host") :]


def test_mrb6955_start_script_and_docs():
    start = START.read_text(encoding="utf-8")
    assert "Test-BobiverseIsChairHost" in start
    assert "skip reason=not_chair_host" in start
    assert "exit 0" in start
    assert "FR #6953" in start
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #6953" in docs
    assert "not_chair_host" in docs
    assert "would_spawn" in docs
    assert not docs.startswith("\ufeff")
