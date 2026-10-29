"""FR #5184: derive priority-customer harvest routing from the shared topic set."""
from __future__ import annotations

from pathlib import Path

import intake
import priority_customer as pc


def test_fr5184_harvest_repos_come_from_saved_topic_set(tmp_path, monkeypatch):
    tagged = {"simonbarnett/hrsmith", "simonbarnett/ce-priority"}
    pc.save_topic_repos(tmp_path, tagged)

    def unexpected_refresh(*_args, **_kwargs):
        raise AssertionError("unexpected refresh")

    monkeypatch.setattr(pc, "refresh_topic_repos", unexpected_refresh)

    repos = intake.priority_customer_harvest_repos(home=tmp_path)

    assert repos == tagged
    assert intake.is_priority_customer_harvest_repo("SimonBarnett/hrsmith", home=tmp_path)
    assert intake.is_priority_customer_harvest_repo("SimonBarnett/ce-priority", home=tmp_path)
    assert not intake.is_priority_customer_harvest_repo("SimonBarnett/not-tagged", home=tmp_path)


def test_fr5184_empty_topic_cache_falls_back_to_topic_search(tmp_path):
    calls = []

    def fetch_json(url):
        calls.append(url)
        return {"items": [{"full_name": "SimonBarnett/new-customer"}]}

    repos = intake.priority_customer_harvest_repos(
        home=tmp_path,
        fetch_json=fetch_json,
    )

    assert repos == {"simonbarnett/new-customer"}
    assert len(calls) == 1
    assert "topic:priority-customer" in calls[0]
    assert pc.load_topic_repos(tmp_path) == repos
    assert intake.is_priority_customer_harvest_repo(
        "SimonBarnett/new-customer", home=tmp_path
    )


def test_fr5184_new_customer_repo_keeps_product_harvest_routing():
    book, path = intake.product_default_skill_book(
        "SimonBarnett/hrsmith", topic_repos={"simonbarnett/hrsmith"}
    )

    assert book == "harvest-agent-skills"
    assert path == ".grok/skills/harvest-agent-skills/SKILL.md"
    assert intake.rewrite_harvest_repo_for_skill_book(
        "SimonBarnett/hrsmith", "bobiverse-bob-worker"
    ) == "SimonBarnett/bobiverse"


def test_fr5184_intake_has_no_hardcoded_priority_customer_list():
    text = Path(intake.__file__).read_text(encoding="utf-8")

    assert "PRIORITY_CUSTOMER_HARVEST_REPOS = frozenset" not in text
    assert '"simonbarnett/euroflo"' not in text
    assert '"simonbarnett/lynton"' not in text
    assert '"simonbarnett/trutex"' not in text
    assert '"simonbarnett/rees"' not in text
