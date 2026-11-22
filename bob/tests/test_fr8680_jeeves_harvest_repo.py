"""BOB-41: Agents > Jeeves harvest cites SimonBarnett/bobiverse."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENTS = (ROOT / "jeeves" / "AGENTS.md").read_text(encoding="utf-8")
SKILL = (ROOT / "jeeves" / ".grok" / "skills" / "jeeves-harvest-bobiverse" / "SKILL.md").read_text(encoding="utf-8")


def test_fr8680_harvest_repo_is_bobiverse():
    assert "BOB-41" in AGENTS
    assert "Invoke-BobiverseHarvest.ps1 -Repo SimonBarnett/bobiverse" in AGENTS
    assert "-Repo SimonBarnett/bobiverse" in SKILL
    assert "https://bob.ntsa.uk/bob/v1/intake" in SKILL
