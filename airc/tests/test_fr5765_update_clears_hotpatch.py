"""FR #5765: successful Airc UPDATE clears the stale hotpatch overlay."""
from __future__ import annotations

from repo_layout import ROOT


UPDATER = ROOT / "common/scripts/Update-BobiverseService.ps1"
DOCS = ROOT / "airc/docs/airc-remote-control.md"


def test_fr5765_apply_clears_hotpatch_after_verified_airc_update():
    updater = UPDATER.read_text(encoding="utf-8-sig")
    apply = updater[updater.index("function Invoke-Apply") : updater.index("function Invoke-Check")]
    marker = apply.index("# FR #5765")
    version_check = apply.index("if (-not $newVer -or $newVer -ne $target)")
    success = apply.index("$script:ApplySucceeded = $true")
    cleanup = apply[marker:success]

    assert version_check < marker < success
    assert "if ($Product -eq 'airc')" in cleanup
    assert "Join-Path $InstallRoot 'HOTPATCH.json'" in cleanup
    assert "Remove-Item -LiteralPath $hotpatchPath -Force -ErrorAction Stop" in cleanup
    assert "Invoke-Rollback -BackupDir $backup" in apply


def test_fr5765_update_marker_behavior_is_documented():
    docs = DOCS.read_text(encoding="utf-8")
    assert "successful Airc UPDATE removes `HOTPATCH.json`" in docs
    assert "rollback restores it" in docs
