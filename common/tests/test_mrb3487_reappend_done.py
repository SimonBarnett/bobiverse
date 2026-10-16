"""MRB #3487: a drained outbox is not a missing board."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"
NEEDLE = (
    "When bob-worker says the turn ended ACKed but no DONE/NACK/GIVEUP, "
    "and this seat already posted the board, re-append that same DONE line. "
    "A drained outbox is not a missing board. Do not re-review the tip."
)


def test_mrb3487_drained_outbox_reappend_same_done():
    skill = SKILL.read_text(encoding="utf-8")
    assert NEEDLE in skill
