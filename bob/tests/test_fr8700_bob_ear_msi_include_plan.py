"""FR #8700 / BOB-49: bob-ear MSI stage includes Plan agent build."""
from __future__ import annotations

from repo_layout import ROOT

PACK = ROOT / "common" / "scripts" / "Pack-BobiverseRelease.ps1"
EVIDENCE = ROOT / "bob" / "docs" / "bob-49-bob-ear-msi-include-plan-evidence.md"


def test_evidence_doc():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-49" in text
    assert "plan" in text.lower()
    assert "heat" in text.lower()
    assert "PlanAgent" in text or "9354" in text


def test_pack_stage_bob_requires_plan_and_marker():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "Stage-BobAgentFolders" in text
    assert "bob pack requires bob-agents\\worker" in text
    assert "bob pack requires bob-agents\\worker and bob-agents\\plan" not in text
    assert "BOB-49" in text
    assert "BOB-49-PLAN-IN-MSI.txt" in text
    assert "bob MSI stage missing plan" in text
    # FR #9354: PlanAgent.exe vendored from skills-visionary
    assert "PlanAgent.exe" in text
    assert "SkipPlanAgentExe" in text
    assert "PlanAgent.MANIFEST.json" in text
