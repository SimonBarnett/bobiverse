"""MRB #3924 docs/hostile: FR #3923 mid-job fuel unknown must not GIVEUP.

Pins contiguous product helpers + skill troubleshooting + harvested lesson.
"""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

ROOT = Path(__file__).resolve().parents[1]
WORKER_PY = ROOT / "scripts" / "bob_worker.py"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
FR_TEST = Path(__file__).resolve().parent / "test_fr3923_mid_job_fuel_unknown.py"


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path} must be UTF-8 without BOM"
    text = raw.decode("utf-8")
    assert text.endswith("\n"), f"{path} needs trailing newline"
    return text


def test_mrb3924_helpers_contiguous_in_bob_worker():
    text = _utf8_no_bom(WORKER_PY)
    assert "def fuel_reading_known(" in text
    assert "def fuel_explicitly_exhausted(" in text
    assert "def format_fuel_reading(" in text
    assert "fuel_lost_streak_need" in text
    assert 'BOB_WORKER_OUT_OF_FUEL_STREAK' in text
    # Unknown must not trip mid-job lost
    assert "Empty ``Fuel()`` (helper missing / timeout / unreadable) is **unknown**, not exhausted." in text or (
        "is **unknown**, not exhausted" in text
    )
    assert "Unknown / unreadable readings must **not** trip mid-job GIVEUP" in text


def test_mrb3924_skill_troubleshoot_and_harvest_lesson():
    text = _utf8_no_bom(SKILL)
    needle_row = (
        "Both Grok seats GIVEUP mid-job while credits remain (`creditUsagePercent` low) | "
        "Mid-job fuel poll treated **unknown**/timeout as exhausted (FR #3923)"
    )
    assert needle_row in text or (
        "Mid-job fuel poll treated **unknown**/timeout as exhausted (FR #3923)" in text
        and "known=False" in text
    )
    lesson = (
        "bob-worker: mid-job fuel-lost poll must treat unknown/timeout Fuel as **not** lost; "
        "only explicit exhausted readings count, and require 2 consecutive polls "
        "(or a 402 log hit) before GIVEUP; log pct/state every poll (FR #3923)."
    )
    assert lesson in text


def test_mrb3924_fr3923_acceptance_tests_present():
    text = _utf8_no_bom(FR_TEST)
    assert "test_a_unknown_fuel_while_ack_open_no_giveup" in text
    assert "test_b_transient_zero_then_recovery_no_giveup" in text
    assert "test_c_two_consecutive_exhausted_giveup" in text
    assert "fuel_explicitly_exhausted" in text


def test_mrb3924_behaviour_unknown_not_exhausted():
    assert bw.fuel_explicitly_exhausted(bw.Fuel(), "grok") is False
    assert bw.fuel_explicitly_exhausted(bw.Fuel(grok_pct=0, grok_state="exhausted"), "grok") is True
