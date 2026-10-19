"""MRB #4737: pin FR #4732 Cursor submit-verify grace in bobiverse-bob-worker."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"


def test_skill_pins_fr4732_turn_open_probe_and_giveup_grace():
    raw = SKILL.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf", "skill must be UTF-8 without BOM"
    assert raw.endswith(b"\n"), "skill must end with LF"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    prior = (
        "bob-worker: FR #4730 --- after DONE/NACK/GIVEUP, a replayed ACK for that "
        "job is dropped before IRC and must not reopen busy; a fresh inject clears "
        "the finished mark so a legitimate re-offer can ACK again (PR #4731)"
    )
    needle = (
        "bob-worker: FR #4732 --- Cursor submit-verify stop is turn_open|probe "
        "(not receipt ACK); after FAILED poll turn_running for "
        "BOB_WORKER_SUBMIT_VERIFY_GIVEUP_GRACE_S before GIVEUP so a landed paste is "
        "not reported failed (PR #4737)"
    )
    window = text[text.find(prior) : text.find(prior) + len(prior) + len(needle) + 8]
    assert prior in window
    assert needle in window
    assert prior + "\n- " + needle in text
    assert "Cursor seats (FR #4510 / #4732)" in text
    assert "BOB_WORKER_SUBMIT_VERIFY_GIVEUP_GRACE_S" in text
