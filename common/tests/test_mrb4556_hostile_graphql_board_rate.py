"""MRB #4556 hostile pin: GraphQL board playbook when REST is rate-limited."""
from pathlib import Path

import repo_layout

REPO = Path(repo_layout.REPO)
SKILL = REPO / "common/.grok/skills/harvest/SKILL.md"
NEEDLE = (
    "When REST core rate-limited, post MRB PASS board via gh api graphql --input JSON file "
    "so PowerShell does not expand dollar vars in the query"
)


def test_mrb4556_hostile_graphql_board_lesson_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert NEEDLE in text
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    assert "rate_remaining" in text