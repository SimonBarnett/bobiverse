"""FR a-search #3907: a skill-book harvest tip must Refs a product issue, never Closes it."""
from __future__ import annotations

import re

from intake import build_lesson_pr_body


def test_session_summary_closes_becomes_refs():
    body = build_lesson_pr_body(
        book="harvest-agent-skills",
        path=".grok/skills/harvest-agent-skills/SKILL.md",
        lessons=["shop connect stubs set contactVerified true"],
        original_body=(
            "Session summary:\n"
            "MRB #3871 PASS; Closes #3867 linked; no fold\n"
        ),
    )
    assert "Closes #3867" not in body
    assert "Refs #3867" in body
    assert "close with a one-line reason" in body or "close citing" in body
    assert not re.search(r"(?i)\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+#\d+", body)


def test_owner_repo_and_lesson_line_become_refs():
    body = build_lesson_pr_body(
        book="harvest-agent-skills",
        path=".grok/skills/harvest-agent-skills/SKILL.md",
        lessons=["Fixes SimonBarnett/a-search#3867 in the product tip"],
        original_body="Resolves #12 and closed SimonBarnett/a-search#99.\n",
    )
    assert "Fixes SimonBarnett/a-search#3867" not in body
    assert "Refs SimonBarnett/a-search#3867" in body
    assert "Resolves #12" not in body
    assert "Refs #12" in body
    assert "closed SimonBarnett/a-search#99" not in body
    assert "Refs SimonBarnett/a-search#99" in body
