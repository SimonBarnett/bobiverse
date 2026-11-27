"""FR #9765: sparse CI builds Watch-AgentHealth.exe via Build-BobWatcher.ps1."""
from __future__ import annotations

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-agentwatcher.yml"
BUILD = ROOT / "bob" / "scripts" / "Build-BobWatcher.ps1"
README = ROOT / "bob" / "agentwatcher" / "README.md"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def test_fr9765_agentwatcher_ci_workflow_pins():
    assert WF.is_file(), "missing .github/workflows/build-bob-agentwatcher.yml"
    text = _wf()
    assert "name: build-bob-agentwatcher" in text
    assert "build-bob-agentwatcher:" in text
    assert "runs-on: windows-latest" in text
    assert "sparse-checkout:" in text
    assert "bob/agentwatcher" in text
    assert "Build-BobWatcher.ps1" in text
    assert "bob/scripts/Build-BobWatcher.ps1" in text
    assert "bob/tests/test_fr9765_agentwatcher_build_ci.py" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "upload-artifact@v4" in text
    assert "name: bob-agentwatcher" in text
    assert "Watch-AgentHealth.exe" in text
    assert "Watch-AgentHealth.exe.sha256" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert "MANIFEST.json" in text
    assert "provenance.txt" in text
    assert "workflow_dispatch" in text
    assert "pyinstaller" in text.lower()
    assert BUILD.is_file()
    build = BUILD.read_text(encoding="utf-8-sig")
    assert "Watch-AgentHealth" in build
    assert "PyInstaller" in build


def test_fr9765_docs_note_watcher_ci():
    text = README.read_text(encoding="utf-8")
    assert "build-bob-agentwatcher.yml" in text
    assert "Build-BobWatcher.ps1" in text
    assert "bob-agentwatcher" in text
    assert "FR #9765" in text
