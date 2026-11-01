"""FR #5765: successful Airc UPDATE removes stale HOTPATCH.json metadata."""
from __future__ import annotations

from repo_layout import ROOT


UPDATER = ROOT / "common/scripts/Update-BobiverseService.ps1"
REMOTE_DOCS = ROOT / "airc/docs/airc-remote-control.md"


def test_fr5765_hotpatch_cleanup_is_airc_only_and_after_success_checks():
    source = UPDATER.read_text(encoding="utf-8-sig")
    apply = source[source.index("function Invoke-Apply") : source.index("# ---------------------------------------------------------------- Check mode")]
    cleanup = apply.index("# FR #5765: release MSI identity")

    assert "$Product -eq 'airc'" in apply[cleanup : cleanup + 600]
    assert "Join-Path $InstallRoot 'HOTPATCH.json'" in apply[cleanup : cleanup + 600]
    assert "Remove-Item -LiteralPath $hotpatch -Force -ErrorAction Stop" in apply[cleanup : cleanup + 600]
    assert apply.index('not running after install') < cleanup
    assert cleanup < apply.index("} catch {", cleanup)
    assert "Invoke-Rollback -BackupDir $backup" in apply


def test_fr5765_version_docs_explain_hotpatch_expiry():
    docs = REMOTE_DOCS.read_text(encoding="utf-8")
    row = next(line for line in docs.splitlines() if "| `VERSION` |" in line)
    assert "successful UPDATE" in row
    assert "HOTPATCH.json" in row
