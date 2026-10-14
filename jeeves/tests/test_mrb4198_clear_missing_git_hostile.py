"""MRB #4198 hostile pins for FR #4197 Clear continue-on-missing-.git.

Pins contiguous script/skill phrases so a mid-bullet splice cannot drop the
pre-check WARN or the try/catch continue path.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
FR_SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"


def test_clear_precheck_warn_contiguous_fr4197():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'Write-Warning ("FR #4197: worktree path or .git missing for {0}; rmdir/prune and continue"' in text
    assert "One broken registration must not abort the rest of the Clear run" in text
    # try/catch around worktree remove (FR #2460 + #4197)
    assert "FR #2460 + FR #4197" in text


def test_fr_skill_fr4197_continue_contiguous():
    text = FR_SKILL.read_text(encoding="utf-8")
    assert (
        "**FR #4197:** Clear must not abort when one registered worktree path or .git is missing"
        in text
    )
    assert "continue reclaiming the rest" in text
