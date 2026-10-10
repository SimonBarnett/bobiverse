"""MRB #3832 hostile pins for FR #3827 FAIL-supersede harvest skip tighten."""
from __future__ import annotations

import inspect
from pathlib import Path

import intake


ROOT = Path(__file__).resolve().parents[2]
HARVEST_SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
MRB_DOC = ROOT / "docs" / "mrb" / "mrb-3832.md"

INCIDENT = (
    "FAIL-supersede / thin harvest restatement playbooks stay in "
    "bobiverse-bob-job-mrb; do not append a second copy under harvest/SKILL.md"
)


def test_incident_3826_blob_matches_process_and_thin_cues():
    assert intake.is_fail_supersede_thin_twin_lesson(INCIDENT)
    assert intake.is_mrb_process_routing_lesson(INCIDENT)
    src = inspect.getsource(intake.is_mrb_process_routing_lesson)
    assert "stay" in src.lower() or "durable" in src.lower()
    assert "second" in src.lower() and "copy" in src.lower()


def test_skill_ps1_and_docs_cite_fr3827():
    skill = HARVEST_SKILL.read_text(encoding="utf-8")
    assert "FR #3827" in skill
    assert "thin harvest tip" in skill.lower() or "stay" in skill.lower()
    ps1 = PS1.read_text(encoding="utf-8")
    assert "3827" in ps1
    assert "thin harvest tip" in ps1.lower() or "stay in" in ps1.lower()
    mrb = MRB_DOC.read_text(encoding="utf-8")
    assert "3827" in mrb or "3832" in mrb
