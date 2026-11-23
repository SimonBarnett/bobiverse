"""FR #9007: non-chair repo-tree installs resolve Sync under common/scripts."""
from __future__ import annotations

from repo_layout import REPO

START = REPO / "jeeves" / "scripts" / "Start-JeevesMonitor.ps1"
INVOKE = REPO / "jeeves" / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
DOCS = REPO / "jeeves" / "docs" / "monitoring.md"


def test_start_resolves_common_scripts_sync():
    text = START.read_text(encoding="utf-8-sig")
    assert "Resolve-SyncBobiverseFromRepoPath" in text
    assert "FR #9007" in text
    assert "common\\scripts\\" in text
    assert "tools\\monitor may stay stale" in text


def test_invoke_check_syncs_before_run():
    text = INVOKE.read_text(encoding="utf-8-sig")
    assert "FR #9007" in text
    assert "Sync-BobiverseFromRepo.ps1" in text
    assert "common\\scripts\\" in text
    # FR #9007 product pin. FR #9350 may pass args via Start-Process ArgumentList
    # ("-Product", "jeeves") instead of an in-process "-Product jeeves" string.
    assert "-Product" in text
    assert "jeeves" in text
    assert (
        "-Product jeeves" in text
        or "'-Product', 'jeeves'" in text
        or '"-Product", "jeeves"' in text
        or ("'-Product'" in text and "'jeeves'" in text)
        or ('"-Product"' in text and '"jeeves"' in text)
    )


def test_docs_cover_repo_tree_sync_path():
    text = DOCS.read_text(encoding="utf-8")
    assert "FR #9007" in text
    assert "common\\scripts" in text or "common/scripts" in text
