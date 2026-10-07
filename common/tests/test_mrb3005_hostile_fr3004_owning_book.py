"""Hostile MRB #3005: soft harvest default yields to owning book; skip when covered (FR #3004)."""
from __future__ import annotations

from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST = ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
HARVEST_PS1 = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"
INTAKE = ROOT / "common" / "scripts" / "intake.py"
WORKER = "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_mrb3005_harvest_skill_pins_fr3004_contiguous():
    t = _read(HARVEST)
    assert "FR #3004" in t
    assert "lesson_already_covered" in t or "owning product book" in t or "owning skill" in t
    raw = HARVEST.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_mrb3005_client_and_intake_gates_present():
    ps1 = _read(HARVEST_PS1)
    assert "FR #3004" in ps1
    assert "bobiverse-bob-worker" in ps1
    py = _read(INTAKE)
    assert "infer_soft_harvest_override" in py
    assert "_SOFT_HARVEST_OVERRIDE_HINTS" in py
    assert "FR #3004" in py


def test_mrb3005_soft_override_strong_cues_only():
    """Bare MRB session summary must stay on harvest; bob-worker cues re-route."""
    book, _ = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: MRB #2997 PASS",
        body="Lessons:\n- MSI SkipCopy when MsiProductVersion set\n",
    )
    assert book == "harvest"
    book2, path2 = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: MRB #2997 PASS",
        body="Lessons:\n- bob-worker: done-miss release must set _release_gen\n",
    )
    assert book2 == "bobiverse-bob-worker"
    assert path2 == WORKER
