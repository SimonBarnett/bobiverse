"""FR #4492: leave an already-armed SQUASH auto-merge; do not flip the method."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDLE = (
    "If auto-merge is already armed as SQUASH, leave it; "
    "do not disable and re-arm just to flip the method (FR #4492)."
)


def test_fr4492_job_mrb_leaves_armed_squash():
    skill = (
        ROOT
        / "bob"
        / ".grok"
        / "skills"
        / "bobiverse-bob-job-mrb"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    cmd = "gh pr merge <n> --repo <owner/repo> --auto --merge"
    idx = skill.find(cmd)
    assert idx >= 0
    window = skill[idx : idx + 700]
    assert NEEDLE in window
    assert "FR #4492" in window


def test_fr4492_sentence_is_not_in_harvest_skill():
    harvest = (
        ROOT / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert NEEDLE not in harvest
