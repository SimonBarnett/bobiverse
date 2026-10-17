"""MRB #4539 hostile pin: FR re-offer uses covering PR when Closes already linked."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "FR re-offer when open covering PR Closes the issue: verify closingIssuesReferences "
    "+ run acceptance pins on tip head, comment on issue, DONE with covering PR URL only"
)


def test_mrb4539_hostile_fr_reoffer_covering_pr_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "closingIssuesReferences" in text
    assert "covering PR URL only" in text
    assert "\u2014" not in NEEDLE and "\u2013" not in NEEDLE