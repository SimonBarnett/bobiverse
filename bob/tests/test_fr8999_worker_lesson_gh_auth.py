"""FR #8999: worker lesson documents stale gh Active-account block."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "lessons.md"


def test_fr8999_worker_lesson_mentions_stale_gh_auth():
    text = LESSONS.read_text(encoding="utf-8")
    assert "FR #8999" in text
    assert "gh_auth_missing" in text
    assert "Active account" in text
    assert "invent GH_TOKEN" in text or "Never invent GH_TOKEN" in text
    assert "hosts.yml" in text
