"""MRB #4644: re-ACK-after-DONE playbook lives in bobiverse-bob-job-irc, not harvest."""

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
    "Jeeves ignores a later ACK of a job this seat already DONE, "
    "and logs duplicate-after-done, unless an offer was stamped after that DONE."
)


def test_reack_after_done_lives_in_job_irc():
    text = SKILL.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    assert "FR #4642" in text
    assert NEEDLE in text
    assert "\u2014" not in NEEDLE
