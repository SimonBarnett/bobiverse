"""MRB #2462 hostile gates for FR #2460 Clear-BobiverseJobWorktrees git stderr StrictMode."""
from __future__ import annotations

import re

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_mrb2462_no_bare_out_host_on_any_git_worktree_call():
    text = _text()
    # Any git worktree remove/prune must stringify; never pipe straight to Out-Host.
    for m in re.finditer(r"& git[^\n]+worktree (remove|prune)[^\n]*", text):
        line = m.group(0)
        assert "| Out-Host" not in line, line
        # Call site continues into a ForEach stringify block nearby.
        window = text[m.start() : m.start() + 350]
        assert 'ForEach-Object { "$_" }' in window, window


def test_mrb2462_git_exit_captured_before_host_loop():
    text = _text()
    start = text.index("Removing worktree $p")
    block = text[start : start + 900]
    assert "$gitExit = $LASTEXITCODE" in block
    # Capture must precede the Write-Host loop over $gitOut.
    assert block.index("$gitExit = $LASTEXITCODE") < block.index("foreach ($line in $gitOut)")
    assert "if ($gitExit -ne 0)" in block
    assert "Remove-Item -LiteralPath $p -Recurse -Force" in block


def test_mrb2462_fr2460_markers_on_remove_and_prune():
    text = _text()
    assert text.count("FR #2460") >= 2
    assert "ErrorRecords" in text or "ErrorRecord" in text
