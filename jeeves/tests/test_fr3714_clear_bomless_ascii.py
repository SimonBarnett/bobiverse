"""FR #3714: Clear-BobiverseJobWorktrees.ps1 must stay BOM-less ASCII (fr3391 gate)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_fr3714_clear_job_worktrees_bomless_ascii():
    """BOM-less *.ps1 with U+2014 (em dash) breaks WinPS 5.1 ANSI parse / fr3391."""
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "prefer ASCII over UTF-8 BOM (FR #3695)"
    text = raw.decode("utf-8")
    bad = [ch for ch in text if ord(ch) > 127]
    assert not bad, (
        "Clear-BobiverseJobWorktrees.ps1 has non-ASCII "
        f"(first U+{ord(bad[0]):04X}); use ASCII '-' not em dash"
    )
    assert "skip this process ($PID) - Clear" in text
    assert "\u2014" not in text
