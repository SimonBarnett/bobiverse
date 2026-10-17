"""MRB #4552 hostile pin: merge-on-green rate-limit playbook is contiguous."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "Merge-on-green: drop closed/merged after one PR GET (no comments); "
    "back off sweeps when rate_remaining is low so pr_exists and !resync keep quota."
)


def test_mrb4552_hostile_merge_on_green_rate_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "rate_remaining" in text
    assert "\u2014" not in NEEDLE and "\u2013" not in NEEDLE