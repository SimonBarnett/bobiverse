"""MRB #4450: fuel playbook home is bobiverse-bob-worker, not harvest."""
from __future__ import annotations

from pathlib import Path

LESSON = (
    "A bob-worker fuel playbook that intake files under harvest/SKILL.md is moved "
    "into bobiverse-bob-worker Harvested lessons and the harvest tip is closed "
    "unmerged once a reviewable worker-skill PR carries the same sentence; pin "
    "that harvest does not also contain it."
)

_BOB = Path(__file__).resolve().parents[1]
_REPO = _BOB.parent


def test_mrb4450_worker_skill_pins_fuel_lesson_home():
    text = (_BOB / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert not text.startswith("\ufeff")
    assert LESSON in text
    line = next(ln for ln in text.splitlines() if "fuel playbook that intake files" in ln)
    assert "\u2014" not in line
    assert "\u2013" not in line


def test_mrb4450_harvest_skill_does_not_repeat_fuel_home_lesson():
    harvest = _REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
    text = harvest.read_text(encoding="utf-8")
    assert "fuel playbook that intake files under harvest/SKILL.md" not in text
