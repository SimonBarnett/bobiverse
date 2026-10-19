"""MRB #4869 hostile pins for FR #4865 abbreviated harvest twin de-dupe."""
from __future__ import annotations

from pathlib import Path

import intake

REPO = Path(__file__).resolve().parents[2]
INTAKE = REPO / "common" / "scripts" / "intake.py"
HARVEST = REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"

FULL = (
    "After agent 402 usage balance exhausted, keep out-of-fuel held until "
    "BOB_WORKER_OUT_OF_FUEL_MIN_HOLD_S and grok pct above "
    "BOB_WORKER_OUT_OF_FUEL_CLEAR_FLOOR_PCT (or turn_ended); never clear on "
    "soft available with pct at or below the floor."
)
ABBREV = (
    "After agent 402 usage balance exhausted, keep out-of-fuel held until "
    "MIN_HOLD_S and pct above CLEAR_FLOOR_PCT (or turn_ended); never clear on "
    "soft available at or below the floor"
)


def test_mrb4869_intake_py_pure_ascii_no_bom():
    raw = INTAKE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert all(b < 128 for b in raw)


def test_mrb4869_harvest_skill_pins_fr4865_contiguous():
    text = HARVEST.read_text(encoding="utf-8")
    assert "FR #4865" in text
    assert "lesson_already_covered" in text
    assert "abbreviated restatement" in text
    # Contiguous playbook window (tip #4863 / env stems).
    assert "MIN_HOLD_S" in text and "BOB_WORKER_OUT_OF_FUEL_MIN_HOLD_S" in text


def test_mrb4869_unrelated_shared_stopwords_not_collapsed():
    existing = f"# Harvest\n\n- {FULL}\n"
    other = (
        "Never keep after soft clear when the seat is mid-turn; "
        "prefer D job trees and write bobiverse-seat immediately"
    )
    assert intake.filter_new_lessons(existing, [other]) == [other]


def test_mrb4869_abbrev_twin_still_dropped():
    existing = f"# Harvest\n\n- {FULL}\n"
    assert intake.filter_new_lessons(existing, [ABBREV]) == []
