"""FR #4976: customer-repo harvest defaults to repo-root harvest-agent-skills.

Topic lookup may be empty (intake box never refreshed). Euroflo must not land
``common/.grok/skills/harvest/SKILL.md``.
"""
from __future__ import annotations

from pathlib import Path

import intake


def test_fr4976_euroflo_harvest_without_topic_set_uses_repo_root_book():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: Euroflo service-call log",
        body="customer hours on hours branch",
        repo="SimonBarnett/euroflo",
        topic_repos=set(),
    )
    assert book == "harvest-agent-skills"
    assert path.replace("\\", "/") == ".grok/skills/harvest-agent-skills/SKILL.md"
    assert "common/.grok/skills/harvest" not in path.replace("\\", "/")


def test_fr4976_bobiverse_harvest_still_common_book():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: chair outbox",
        body="fleet",
        repo="SimonBarnett/bobiverse",
        topic_repos=set(),
    )
    assert path.replace("\\", "/") == "common/.grok/skills/harvest/SKILL.md"


def test_fr4976_ce_priority_still_dayworks():
    book, path = intake.resolve_skill_book(
        skill_book="harvest",
        title="harvest: tip",
        body="x",
        repo="SimonBarnett/ce-priority",
        topic_repos=set(),
    )
    assert book == "dayworks-launcher"
    assert "dayworks/.grok/skills/dayworks-launcher/SKILL.md" in path.replace("\\", "/")


def test_fr4976_harvest_ps1_maps_other_simonbarnett_to_root_book():
    text = Path(__file__).resolve().parents[2].joinpath(
        "common", "scripts", "Invoke-BobiverseHarvest.ps1"
    ).read_text(encoding="utf-8")
    assert "FR #4976" in text
    assert "not common/.grok/skills/harvest" in text
