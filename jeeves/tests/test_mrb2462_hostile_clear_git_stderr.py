"""Hostile MRB #2462: Clear worktrees capture LASTEXITCODE; FR #8023 keeps failed removes."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_hostile_remove_captures_exit_before_fallback():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("Removing worktree $p")
    block = text[start : start + 2800]
    needle = "$_ -is [System.Management.Automation.ErrorRecord]"
    i_stringify = block.index(needle)
    assert "ToString()" in block[i_stringify : i_stringify + 200]
    assert 'else { "$_" }' in block
    i_exit = block.index("$gitExit = $LASTEXITCODE")
    i_fail = block.index("if ($gitExit -ne 0)")
    # FR #8023: failed remove keeps the dir (no Remove-Item / PathForce fallback).
    assert "kept-remove-failed" in block[i_fail : i_fail + 400]
    assert "Remove-BobiversePathForce -Path $p" not in block[i_fail : i_fail + 400]
    assert i_stringify < i_exit < i_fail


def test_hostile_no_bare_outhost_on_git_native():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("& git -C $rootFull worktree") >= 2
    for marker in ("worktree remove $p", "worktree prune"):
        i = text.index(marker)
        window = text[max(0, i - 80) : i + 200]
        assert "| Out-Host" not in window
        assert "worktree remove --force" not in window
