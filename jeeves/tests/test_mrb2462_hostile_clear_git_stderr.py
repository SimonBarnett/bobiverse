"""Hostile MRB #2462: Clear worktrees capture LASTEXITCODE after stringify, then rmdir fallback."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_hostile_remove_captures_exit_before_fallback():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("Removing worktree $p")
    block = text[start : start + 900]
    i_stringify = block.index('ForEach-Object { "$_" }')
    i_exit = block.index("$gitExit = $LASTEXITCODE")
    i_fallback = block.index("if ($gitExit -ne 0)")
    i_rm = block.index("Remove-Item -LiteralPath $p")
    assert i_stringify < i_exit < i_fallback < i_rm
    assert "will try prune / rmdir" in block


def test_hostile_no_bare_outhost_on_git_native():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.count("& git -C $rootFull worktree") >= 2
    for marker in ("worktree remove --force $p", "worktree prune"):
        i = text.index(marker)
        window = text[max(0, i - 80) : i + 200]
        assert "| Out-Host" not in window
