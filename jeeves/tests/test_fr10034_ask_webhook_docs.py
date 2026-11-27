"""FR #10034: /bob/v1/ask is listed in the jeeves webhook docs and skill."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBHOOKS = ROOT / "docs" / "webhooks.md"
SKILL = ROOT / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"


def test_fr10034_ask_path_listed():
    docs = WEBHOOKS.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    assert "| POST | `/bob/v1/ask` |" in docs
    assert "/bob/v1/ask/health" in docs
    assert "BOB_ASK_ALLOWLIST" in docs
    assert "/bob/v1/ask" in skill
    assert "BOB_ASK_ALLOWLIST" in skill
