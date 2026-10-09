"""MRB #3710 hostile pins for FR #3698 Clear foreign-pid + leaf + WARN."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SCRIPT = ROOT / "common/scripts/Clear-BobiverseJobWorktrees.ps1"
FLEET = ROOT / "common/.grok/skills/bobiverse-fleet-ops/SKILL.md"
FR_SKILL = ROOT / "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md"


def test_mrb3710_script_foreign_pid_and_warn_pins():
    t = SCRIPT.read_text(encoding="utf-8")
    assert "FR #3698" in t
    assert "function Test-ProcessCitesPath" in t
    assert "skipped_other_volume" in t or "other volume" in t.lower()
    assert "WARN FR #3698" in t or ("Write-Warning" in t and "3698" in t)
    assert "ProcessId -ne `$selfPid" in t or "ProcessId -ne $selfPid" in t or "$selfPid" in t


def test_mrb3710_leaf_matcher_keeps_suffix_and_bobiverse_segment():
    """Prefix -\\d (not end-anchored) + optional name segment (MRB tip fix)."""
    t = SCRIPT.read_text(encoding="utf-8")
    block = t[t.find("function Test-IsJobWorktreePath") : t.find("function Test-ProcessCitesPath")]
    assert "(-[a-z0-9_.]+)?" in block or "bobiverse" in block.lower()
    # Must not require end-only -\\d+$ alone (that dropped job-fr-3641-unmarked).
    assert "(-[a-z0-9_.]+)*-\\d+$" not in block
    assert "(fr|mrb|uat|docs-mrb)(-[a-z0-9_.]+)?-\\d" in block or "(fr|mrb|uat|docs-mrb)-\\d" in block


def test_mrb3710_skills_mention_3698():
    assert "3698" in FLEET.read_text(encoding="utf-8")
    fr = FR_SKILL.read_text(encoding="utf-8")
    assert "3698" in fr or "Clear-BobiverseJobWorktrees" in fr
