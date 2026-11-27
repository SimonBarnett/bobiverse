"""FR #9778: jeeves release pack takes www from the webhooks artifact."""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
MSI = ROOT / ".github" / "workflows" / "build-jeeves-msi.yml"


def test_fr9778_release_path_requires_webhooks_artifact():
    text = PACK.read_text(encoding="utf-8")
    assert "[string]$WebhooksArtifactDir" in text
    assert "BOB_WEBHOOKS_ARTIFACT_DIR" in text
    assert "missing MANIFEST.json under WebhooksArtifactDir" in text
    assert "staged www from webhooks artifact" in text
    release, _, tests = text.partition("if (-not $SkipMsi)")
    assert "Copy-Item" in text
    guarded = tests.split("else {", 1)[0]
    assert "jeeves\\www" not in guarded
    assert "Get-BobiverseRepoPath -Root $RepoRoot -Rel 'jeeves\\www'" not in release
    msi = MSI.read_text(encoding="utf-8")
    assert "-WebhooksArtifactDir" in msi
    assert "jeeves_webhooks_ci.py" in msi
