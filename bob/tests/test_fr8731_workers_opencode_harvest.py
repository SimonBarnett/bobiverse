"""FR #8731 / BOB-32: Workers > OpenCode harvest targets SimonBarnett/bobiverse."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDLE = "Workers > OpenCode harvest (FR #8731)"
REPO = "SimonBarnett/bobiverse"


def test_fr8731_agents_skill_and_prompt_cite_bobiverse():
    agents = (ROOT / "bob" / "agents" / "worker" / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(encoding="utf-8")
    prompt = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    docs = (ROOT / "bob" / "docs" / "fr-8731-workers-opencode-harvest-evidence.md").read_text(encoding="utf-8")
    for name, text in (("AGENTS", agents), ("skill", skill), ("prompt", prompt)):
        assert NEEDLE in text, name
        assert REPO in text, name
        assert "Do not file them on a-search" in text, name
    assert "FR #8731" in docs
    assert REPO in docs
