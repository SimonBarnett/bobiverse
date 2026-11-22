"""FR #8718 / BOB-25: Workers > Cursor harvest targets SimonBarnett/bobiverse."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEEDLE = "Workers > Cursor harvest (FR #8718)"
REPO = "SimonBarnett/bobiverse"


def test_fr8718_agents_skill_and_prompt_cite_bobiverse():
    agents = (ROOT / "bob" / "agents" / "worker" / "AGENTS.md").read_text(encoding="utf-8")
    skill = (ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md").read_text(encoding="utf-8")
    prompt = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    docs = (ROOT / "bob" / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    for name, text in (("AGENTS", agents), ("skill", skill), ("prompt", prompt)):
        assert NEEDLE in text, name
        assert REPO in text, name
        assert "Do not file them on a-search" in text, name
    assert "FR #8718" in docs
    assert REPO in docs
