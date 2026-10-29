"""FR #5184: harvest routing follows the saved priority-customer topic."""
from __future__ import annotations

import intake
import priority_customer as pc


def test_fr5184_cached_topic_repos_drive_harvest_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    pc.save_topic_repos(tmp_path, ["SimonBarnett/hrsmith", "SimonBarnett/ce-priority"])

    topics = intake._priority_customer_topic_repos(home=tmp_path)
    assert topics == {"simonbarnett/hrsmith", "simonbarnett/ce-priority"}
    assert intake.lesson_owner_repo(
        title="harvest: HRSmith customer forms",
        body="Customer-specific field mapping.",
        topic_repos=topics,
    ).repo == "SimonBarnett/hrsmith"
    assert intake.lesson_owner_repo(
        title="harvest: ce-priority launcher",
        body="Customer-specific deployment flow.",
        topic_repos=topics,
    ).repo == "SimonBarnett/ce-priority"
    assert intake.lesson_owner_repo(
        title="harvest: unrelated customer forms",
        body="Generic example with no tagged repository.",
        topic_repos=topics,
    ).repo is None


def test_fr5184_missing_or_empty_cache_falls_back_to_topic_search(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))

    for existing_cache in (False, True):
        if existing_cache:
            pc.save_topic_repos(tmp_path, [])

        calls = []

        def fetch_json(url):
            calls.append(url)
            return {
                "items": [
                    {"full_name": "SimonBarnett/hrsmith"},
                    {"full_name": "SimonBarnett/ce-priority"},
                ]
            }

        topics = intake._priority_customer_topic_repos(
            home=tmp_path, fetch_json=fetch_json
        )
        assert topics == {"simonbarnett/hrsmith", "simonbarnett/ce-priority"}
        assert len(calls) == 1
        assert "topic:priority-customer" in calls[0]
        assert pc.load_topic_repos(tmp_path) == topics
        (tmp_path / pc.TOPIC_FILE).unlink()
