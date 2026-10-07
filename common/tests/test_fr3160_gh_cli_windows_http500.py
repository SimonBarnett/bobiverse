"""FR #3160: gh-cli-windows skill documents HTTP 500 issues-PATCH close fallback."""
from pathlib import Path

from repo_layout import REPO


def test_gh_cli_windows_skill_http500_fallback():
    p = REPO / "common" / ".grok" / "skills" / "gh-cli-windows" / "SKILL.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "HTTP 500" in text
    assert "issues" in text and "state=closed" in text
    assert "FR #3160" in text
    assert "gh api --method PATCH" in text