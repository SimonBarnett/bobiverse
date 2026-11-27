"""FR #9766: Pack stages prebuilt tray/status/watcher exes and does not rebuild them."""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"


def test_fr9766_pack_does_not_invoke_dialog_or_watcher_build():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "Copy-BobPrebuiltExe" in text
    assert "TrayArtifactDir" in text
    assert "StatusArtifactDir" in text
    assert "WatcherArtifactDir" in text
    assert "BOB_TRAY_ARTIFACT" in text
    assert "BOB_STATUS_ARTIFACT" in text
    assert "BOB_WATCHER_ARTIFACT" in text
    assert "& $buildDialogs" not in text
    assert "& $buildWatcher" not in text
    assert "missing bob-tray.exe" in text or 'throw "missing $Name"' in text
    assert "Build-BobDialogs.ps1 -RepoRoot" not in text
    assert "Build-BobWatcher.ps1" not in text or "do not call Build-BobWatcher.ps1" in text


def test_fr9766_docs_name_artifact_inputs():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #9766" in docs
    assert "TrayArtifactDir" in docs or "BOB_TRAY_ARTIFACT" in docs
    assert "does not rebuild" in docs or "must not rebuild" in docs
