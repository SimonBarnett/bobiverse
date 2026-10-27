"""Hostile MRB #5089: nick_in_giveup_seats must not call nick_inherits_dead_seat."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mrb5089_giveup_helper_does_not_call_inherit():
    src = (ROOT / "common" / "scripts" / "gitclaim.py").read_text(encoding="utf-8")
    start = src.index("def nick_in_giveup_seats(")
    end = src.index("\ndef _channel(", start)
    body = src[start:end]
    assert "do not call nick_inherits_dead_seat" in body
    assert "nick_inherits_dead_seat(" not in body
    assert "FR #5088" in body
