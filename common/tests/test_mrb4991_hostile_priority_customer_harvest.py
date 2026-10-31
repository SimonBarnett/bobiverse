"""docs/mrb-4991: priority-customer harvest-agent-skills PRODUCT_DEFAULT + PS1 branch."""
from __future__ import annotations

from pathlib import Path

import intake
from repo_layout import ROOT

HARVEST_PS1 = ROOT / "common" / "scripts" / "Invoke-BobiverseHarvest.ps1"

PRIORITY = (
    "simonbarnett/rees",
    "simonbarnett/lynton",
    "simonbarnett/trutex",
    "simonbarnett/euroflo",
)


def test_mrb4991_product_default_and_ps1_regex():
    for key in PRIORITY:
        assert key in intake.PRODUCT_DEFAULT_SKILL_BOOK
        book, path = intake.PRODUCT_DEFAULT_SKILL_BOOK[key]
        assert book == "harvest-agent-skills"
        assert "harvest-agent-skills" in path.replace("\\", "/")
        assert "common/.grok/skills/harvest/SKILL.md" not in path.replace("\\", "/")
    text = HARVEST_PS1.read_text(encoding="utf-8")
    assert "FR #4990" in text
    assert "euroflo|lynton|trutex|rees" in text
    got = intake.harvest_priority_customer_repos(
        topic_repos={"SimonBarnett/rees", "SimonBarnett/hrsmith"}
    )
    assert "simonbarnett/rees" in got
    assert "simonbarnett/hrsmith" in got
