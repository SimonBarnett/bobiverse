"""MRB #4190 hostile pins for FR #4181 out-of-fuel giveup-offer skip.

Contiguous needles so a mid-function splice cannot drop the mark / skip /
!bored clear path while leaving FR unit tests looking green.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITCLAIM = REPO / "common" / "scripts" / "gitclaim.py"
IRC_AGENT = REPO / "common" / "scripts" / "irc_agent.py"
FR_TEST = REPO / "jeeves" / "tests" / "test_fr4181_out_of_fuel_no_giveup_offer.py"


def test_gitclaim_out_of_fuel_mark_api_contiguous():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert 'SEAT_OUT_OF_FUEL_NAME = "seat-out-of-fuel.json"' in text
    assert "def is_out_of_fuel_reason(reason: str) -> bool:" in text
    assert 'token == "out-of-fuel"' in text
    assert "def seat_is_out_of_fuel(home: Path, nick: str" in text
    assert "def note_seat_out_of_fuel(home: Path, nick: str" in text
    assert "def clear_seat_out_of_fuel(home: Path, nick: str" in text
    assert "if seat_is_out_of_fuel(home, nick, now):" in text
    assert "if seat_is_out_of_fuel(home, nick, now_f):" in text


def test_irc_agent_skips_giveup_offer_on_out_of_fuel_contiguous():
    text = IRC_AGENT.read_text(encoding="utf-8")
    assert "if verb == \"GIVEUP\" and gitclaim.is_out_of_fuel_reason(reason):" in text
    assert "gitclaim.note_seat_out_of_fuel(self._digest_home(), src, reason=reason)" in text
    assert "giveup-offer skipped nick=" in text
    assert "reason=out-of-fuel" in text
    assert "gitclaim.clear_seat_out_of_fuel(self.home, src)" in text
    assert "out-of-fuel cleared nick=" in text
    assert "via=!bored" in text


def test_fr4181_suite_documents_skip_and_bored_clear():
    text = FR_TEST.read_text(encoding="utf-8")
    assert "out-of-fuel must not giveup-offer" in text
    assert "test_out_of_fuel_giveup_marks_seat_and_skips_offer" in text
    assert "clear_seat_out_of_fuel" in text or "!bored" in text
    assert "FR #2811" in text
