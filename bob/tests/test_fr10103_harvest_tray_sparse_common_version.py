"""Harvest #10103: tray/status sparse CI must checkout common/VERSION for split-repo paths."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

TRAY_WF = ROOT / ".github" / "workflows" / "build-bob-tray.yml"
STATUS_WF = ROOT / ".github" / "workflows" / "build-bob-status.yml"
BUILD = ROOT / "bob" / "scripts" / "Build-BobDialogs.ps1"
CM = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"
LOG = ROOT / "common" / "docs" / "skill-harvest-log.md"
FLEET = ROOT / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"


def test_fr10103_tray_and_status_sparse_include_common_version():
    tray = TRAY_WF.read_text(encoding="utf-8")
    status = STATUS_WF.read_text(encoding="utf-8")
    for text in (tray, status):
        assert "sparse-checkout:" in text
        assert "common/VERSION" in text
        assert "Bobiverse-Common.ps1" in text


def test_fr10103_build_bobdialogs_documents_version_belt():
    text = BUILD.read_text(encoding="utf-8")
    assert "FR #10103" in text
    assert "common\\VERSION" in text or "common/VERSION" in text
    assert "bob\\tray\\dialogs" in text
    cm = CM.read_text(encoding="utf-8")
    assert "function Test-BobiverseSplitRepo" in cm
    assert "common\\VERSION" in cm


def test_fr10103_harvest_promote_pins():
    docs = DOCS.read_text(encoding="utf-8-sig")
    assert "FR #10103" in docs or "harvest #10103" in docs
    assert "common/VERSION" in docs
    fleet = FLEET.read_text(encoding="utf-8")
    assert "10103" in fleet
    log = LOG.read_text(encoding="utf-8")
    assert "10103" in log
    assert "common/VERSION" in log
    assert "<<<<<<" not in log


def test_fr10103_files_end_with_newline():
    for p in (Path(__file__), BUILD, DOCS):
        assert p.read_bytes().endswith(b"\n"), p
