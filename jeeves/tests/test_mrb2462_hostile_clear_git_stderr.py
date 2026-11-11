"""Hostile MRB #2462: Clear worktrees capture LASTEXITCODE after stringify, then rmdir fallback."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_hostile_remove_captures_exit_before_fallback():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("Removing worktree $p")
    block = text[start : start + 2200]
    # FR #2460 / #4197: multi-line ErrorRecord stringify (legacy one-liner still ok).
    if 'ForEach-Object { "$_" }' in block:
        i_stringify = block.index('ForEach-Object { "$_" }')
    else:
        # Prefer the type-check line, not the FR #4197 comment that says ErrorRecords.
        needle = "$_ -is [System.Management.Automation.ErrorRecord]"
        i_stringify = block.index(needle)
        assert "ToString()" in block[i_stringify : i_stringify + 200]
        assert 'else { "$_" }' in block
    i_exit = block.index("$gitExit = $LASTEXITCODE")
    i_fallback = block.index("if ($gitExit -ne 0)")
    # FR #3717: leftover path after failed remove uses Remove-BobiversePathForce.
    i_rm = block.index("Remove-BobiversePathForce -Path $p", i_fallback)
    assert i_stringify < i_exit < i_fallback < i_rm
    assert "will try prune / rmdir" in block


def test_hostile_no_bare_outhost_on_git_native():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("& git -C $rootFull worktree") >= 2
    for marker in ("worktree remove --force $p", "worktree prune"):
        i = text.index(marker)
        window = text[max(0, i - 80) : i + 280]
        assert "| Out-Host" not in window
