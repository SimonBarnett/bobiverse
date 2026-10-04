from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_owner_books_and_flow_diagrams_are_canonical():
    required = {
        "bob/.grok/skills/bobiverse-bob-worker/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-fr/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-mrb/SKILL.md",
        "bob/.grok/skills/bobiverse-bob-job-uat/SKILL.md",
        "common/.grok/skills/bobiverse-fleet-ops/SKILL.md",
        "common/.grok/skills/harvest-agent-skills/SKILL.md",
        "jeeves/.grok/skills/bobiverse-jeeves-monitor/SKILL.md",
    }
    for rel in required:
        text = (ROOT / rel).read_text(encoding="utf-8-sig")
        assert "```mermaid" in text, rel
        assert "2026-10-04" in text, rel


def test_installers_and_agent_projection_keep_product_books_vendored():
    common = (ROOT / "common/scripts/Bobiverse-Common.ps1").read_text(encoding="utf-8-sig")
    bob = (ROOT / "bob/scripts/Install-Bob.ps1").read_text(encoding="utf-8-sig")
    jeeves = (ROOT / "jeeves/scripts/Install-Jeeves.ps1").read_text(encoding="utf-8-sig")
    for text in (bob, jeeves):
        assert "Install-BobiverseAgentLayer" in text
        assert "Install-BobiverseSkills" in text
    assert "Get-BobiverseSkillNames" in common
    assert "bobiverse-bob-worker" in common
    assert "bobiverse-fleet-ops" in common
    assert "harvest-agent-skills" in common
