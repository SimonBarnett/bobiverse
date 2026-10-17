"""FR #4647: fetch origin inside a separate job clone before a behind-main fold."""

from pathlib import Path


SKILL = (
    Path(__file__).resolve().parents[2]
    / "bob"
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)

NEEDLE = (
    "a job tree that is its own clone does not see a fetch run in another clone. "
    "Before the behind-main fold, run `git fetch origin` inside that job tree and "
    "merge that tree's `origin/main`. Do not fold a stale `origin/main` taken from "
    "a different clone."
)


def test_separate_clone_fetch_before_fold():
    text = SKILL.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    assert "FR #4647" in text
    assert NEEDLE in text
    assert "\u2014" not in NEEDLE
