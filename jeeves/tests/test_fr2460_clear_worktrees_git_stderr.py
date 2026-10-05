"""FR #2460: Clear-BobiverseJobWorktrees must not die on git stderr under StrictMode Stop."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_worktree_remove_stringifies_git_stderr():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #2460" in text
    assert "worktree remove --force" in text
    # Must stringify piped records (ForEach-Object { "$_" }) before Write-Host.
    assert 'ForEach-Object { "$_" }' in text or "ForEach-Object { \"`$_\" }" in text
    assert "$gitExit = $LASTEXITCODE" in text or "$gitExit=$LASTEXITCODE" in text.replace(" ", "")
    # Must not use bare Out-Host on git remove (that path terminated on Permission denied).
    remove_block_start = text.index("Removing worktree $p")
    remove_block = text[remove_block_start : remove_block_start + 800]
    assert "| Out-Host" not in remove_block
    assert 'ForEach-Object { "$_" }' in remove_block


def test_worktree_prune_also_stringifies_stderr():
    text = SCRIPT.read_text(encoding="utf-8")
    prune_idx = text.index("Pruning worktree metadata")
    prune_block = text[prune_idx : prune_idx + 500]
    assert 'ForEach-Object { "$_" }' in prune_block
    assert "| Out-Host" not in prune_block
