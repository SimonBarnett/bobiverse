"""FR #4508: re-append DONE only when the head is unchanged and 0 behind."""

from pathlib import Path


SKILL = (
    Path(__file__).resolve().parents[2]
    / "bob"
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-irc"
    / "SKILL.md"
)

NEEDLE = (
    "When bob-worker says the turn ended ACKed but no DONE/NACK/GIVEUP, "
    "re-append the same DONE only when this seat already posted the board, "
    "the head SHA is unchanged, and the tip is 0 behind. If the head moved "
    "or the tip is behind, re-verify. A drained outbox is not a missing board."
)


def test_reappend_done_only_when_head_unchanged_and_not_behind():
    text = SKILL.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    assert NEEDLE in text
    assert "Do not re-review the tip." not in text
    assert "\u2014" not in NEEDLE
