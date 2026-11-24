"""FR #9500: Clear-BobiverseJobWorktrees must not abort on Access denied rmdir."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def test_fr9500_remove_path_force_catches_access_denied():
    text = SCRIPT.read_text(encoding="utf-8")
    assert not SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "FR #9500" in text
    start = text.index("function Remove-BobiversePathForce")
    # Window covers try/catch rmdir + attrib retry + Remove-Item fallback.
    block = text[start : start + 2200]
    assert "try {" in block
    assert "catch {" in block
    assert "rmdir /s /q" in block
    assert "Access denied" in block or "FR #9500" in block
    assert "Write-Warning" in block
    assert "PYTEST~1" in block or ".pytest_cache" in block
    assert "attrib.exe -R" in block or "attrib -R" in block
    # Must not leave a bare cmd rmdir that can terminate StrictMode Stop.
    # First rmdir in this function is inside try (FR #9500).
    assert "cmd.exe /c ('rmdir /s /q" in block
    bare = [
        ln
        for ln in block.splitlines()
        if "rmdir /s /q" in ln and "cmd.exe" in ln
    ]
    assert bare, "expected cmd rmdir lines"
    # Every cmd rmdir line in this function should sit under a try (string pin:
    # try appears before first rmdir).
    assert block.index("try {") < block.index("rmdir /s /q")


def test_fr9500_deep_worktree_cdk_rmdir_also_caught():
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("function Remove-BobiverseDeepWorktreeDirs")
    end = text.index("function Remove-BobiversePathForce")
    block = text[start:end]
    assert "FR #9500" in block
    assert "try {" in block
    assert "catch {" in block
    assert "Write-Warning" in block
