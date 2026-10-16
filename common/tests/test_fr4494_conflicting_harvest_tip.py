"""FR #4494: rebuild a CONFLICTING harvest tip from main; never soft-reset a dirty tip."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDLE = (
    "When a harvest tip is CONFLICTING, branch from current `origin/main`, "
    "add only the lesson and its hostile pin, then `force-with-lease`. "
    "Never `git reset --soft origin/main` on a dirty tip (FR #4494)."
)


def test_fr4494_job_mrb_rebuilds_conflicting_harvest_tip():
    skill = (
        ROOT
        / "bob"
        / ".grok"
        / "skills"
        / "bobiverse-bob-job-mrb"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    anchor = "force-push an empty main tip"
    idx = skill.find(anchor)
    assert idx >= 0
    window = skill[idx : idx + 500]
    assert NEEDLE in window
