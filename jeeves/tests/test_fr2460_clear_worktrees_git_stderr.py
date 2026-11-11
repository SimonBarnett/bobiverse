"""FR #2460: Clear-BobiverseJobWorktrees must not die on git stderr under StrictMode Stop."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def _stringifies_stderr(block: str) -> bool:
    """FR #2460 / #4197: ErrorRecord.ToString() + else { "$_" } (or legacy one-liner)."""
    if 'ForEach-Object { "$_" }' in block:
        return True
    return (
        "ForEach-Object" in block
        and "ErrorRecord" in block
        and "ToString()" in block
        and 'else { "$_" }' in block
    )


def test_worktree_remove_stringifies_git_stderr():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #2460" in text
    assert "FR #4197" in text
    assert "worktree remove --force" in text
    assert _stringifies_stderr(text)
    assert "$gitExit = $LASTEXITCODE" in text or "$gitExit=$LASTEXITCODE" in text.replace(" ", "")
    # Must not use bare Out-Host on git remove (that path terminated on Permission denied).
    remove_block_start = text.index("Removing worktree $p")
    remove_block = text[remove_block_start : remove_block_start + 1600]
    assert "| Out-Host" not in remove_block
    assert _stringifies_stderr(remove_block)
    assert "$gitExit = $LASTEXITCODE" in remove_block


def test_worktree_prune_also_stringifies_stderr():
    text = SCRIPT.read_text(encoding="utf-8")
    prune_idx = text.index("Pruning worktree metadata")
    prune_block = text[prune_idx : prune_idx + 900]
    assert _stringifies_stderr(prune_block)
    assert "| Out-Host" not in prune_block
