"""MRB #3828 hostile pins for FR #3824 harvest open lesson twin skip."""
from __future__ import annotations

import inspect
from pathlib import Path

import intake
from intake import find_open_harvest_lesson_twin


ROOT = Path(__file__).resolve().parents[2]
HARVEST_SKILL = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"
MRB_DOC = ROOT / "docs" / "mrb" / "mrb-3828.md"


def test_find_open_harvest_lesson_twin_exported_and_docs_pin_fr3824():
    assert callable(find_open_harvest_lesson_twin)
    src = inspect.getsource(find_open_harvest_lesson_twin)
    assert "FR #3824" in src or "3824" in src
    assert "seat" in src.lower()
    skill = HARVEST_SKILL.read_text(encoding="utf-8")
    assert "FR #3824" in skill
    assert "seat+lesson" in skill or "seat+normalized" in skill
    assert "open_lesson_twin" in skill or "open harvest-lesson" in skill.lower()
    ps1 = PS1.read_text(encoding="utf-8")
    assert "Test-HarvestOpenLessonTwin" in ps1
    assert "FR #3824" in ps1
    mrb = MRB_DOC.read_text(encoding="utf-8")
    assert "#3828" in mrb or "3824" in mrb


def test_open_lesson_twin_settled_states_include_filing():
    # file_submission settles filing / open_lesson_twin (product pin covers behaviour)
    text = (ROOT / "common" / "scripts" / "intake.py").read_text(encoding="utf-8")
    assert 'rec["state"] = "open_lesson_twin"' in text or "open_lesson_twin" in text
    assert '"filing"' in text or "state=filing" in text or '"state": "filing"' in text
    assert "list_open_pulls" in text or "_filer_list_open_pulls" in text
