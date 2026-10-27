"""Hostile pin MRB #5023 / FR #5022 Clear prelude PSScriptRoot guard."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
SKILL = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"


def test_mrb5023_pins_psscriptroot_guard_and_ref_exclude():
    t = SCRIPT.read_text(encoding="utf-8")
    assert not t.startswith("\ufeff")
    assert "if ($PSScriptRoot)" in t
    assert t.find("if ($PSScriptRoot)") < t.find("Join-Path $PSScriptRoot 'Bobiverse-Common.ps1'")
    assert "-notmatch '(?i)-ref-\\d'" in t
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #5022" in skill
    assert "a-search-ref-4003" in skill
    assert "Join-Path $PSScriptRoot" in skill