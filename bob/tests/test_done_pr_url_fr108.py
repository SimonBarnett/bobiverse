"""FR #108: FR/job-irc skills must require capturing gh pr create URL before DONE."""
from __future__ import annotations

from pathlib import Path

FR = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
IRC = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-irc" / "SKILL.md"


def test_fr_skill_documents_capture_gh_pr_create_url():
    text = FR.read_text(encoding="utf-8")
    assert "FR #108" in text
    assert "gh pr create" in text
    assert "capture" in text.lower() or "$url" in text
    assert "never guess" in text.lower() or "Do not invent" in text or "Never guess" in text


def test_job_irc_skill_points_at_fr108_done_url_rule():
    text = IRC.read_text(encoding="utf-8")
    assert "FR #108" in text
    assert "gh pr create" in text
