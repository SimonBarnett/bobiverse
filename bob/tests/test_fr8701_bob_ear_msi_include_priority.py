"""FR #8701 / BOB-55: bob-ear MSI stage includes PriorityAgent.exe."""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-55-bob-ear-msi-include-priority-evidence.md"
FIXTURE = ROOT / "bob" / "tests" / "fixtures" / "PriorityAgent.exe"


def test_evidence_and_fixture():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-55" in text
    assert "PriorityAgent.exe" in text
    assert FIXTURE.is_file()
    assert FIXTURE.read_bytes()[:2] == b"MZ"


def test_pack_stages_priority_agent():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "BOB-55" in text
    assert "PriorityAgent.exe" in text
    assert "SkipPriorityExe" in text
    assert "BOB-55-PRIORITY-IN-MSI.txt" in text
    assert "priority\\PriorityAgent.exe" in text or "priority/PriorityAgent.exe" in text