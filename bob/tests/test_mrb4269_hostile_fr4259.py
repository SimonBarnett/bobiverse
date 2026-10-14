"""MRB #4269 hostile pins for FR #4259 repeat-DONE / harvest-expiry held flush."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "bob" / "scripts" / "bob_worker.py"
SKILL = REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
FR_TEST = REPO / "bob" / "tests" / "test_fr4259_held_assign_harvest.py"


def test_bob_worker_fr4259_repeat_done_and_expiry_flush_contiguous():
    text = WORKER.read_text(encoding="utf-8")
    assert "FR #4259: repeat DONE after turn_ended must not re-arm harvest." in text
    assert "bored: ignore repeat DONE (already fired !bored)" in text
    assert "bored: ignore repeat DONE after turn_ended (harvest already released)" in text
    assert "def _flush_held_on_harvest_expiry(self, now: float) -> None:" in text
    assert "bored: harvest expired - released" in text
    assert "self._flush_held_on_harvest_expiry(now)" in text


def test_bob_worker_skill_documents_fr4259():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4259" in text
    assert "_flush_held_on_harvest_expiry" in text
    assert "repeat DONE" in text


def test_fr4259_suite_covers_repeat_and_expiry():
    text = FR_TEST.read_text(encoding="utf-8")
    assert "test_fr4259_repeat_done_after_turn_ended_does_not_rearm_harvest" in text
    assert "test_fr4259_harvest_expiry_releases_held_assign_and_allows_bored" in text
    assert "test_fr4259_idle_bored_after_expiry_when_only_held_flag" in text
