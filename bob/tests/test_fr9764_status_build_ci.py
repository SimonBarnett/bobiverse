"""FR #9764: sparse CI builds bob-status.exe only."""
from __future__ import annotations

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-status.yml"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"


def test_fr9764_status_ci_workflow_pins():
    text = WF.read_text(encoding="utf-8")
    assert "name: build-bob-status" in text
    assert "build-bob-status:" in text
    assert "sparse-checkout:" in text
    assert "bob/tray/dialogs" in text
    assert "-Targets status" in text
    assert "name: bob-status" in text
    assert "bob-status.exe" in text
    assert "xAI weekly" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "upload-artifact@v4" in text
    assert "bob-tray.exe" not in text or "also built bob-tray.exe" in text


def test_fr9764_docs_status_ci():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #9764" in docs
    assert "build-bob-status.yml" in docs
    assert "sparse-checkout" in docs
    assert "bob-status" in docs
