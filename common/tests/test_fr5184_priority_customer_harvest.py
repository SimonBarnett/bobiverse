"""FR #5184: derive priority-customer harvest routing from the shared topic set."""
from __future__ import annotations

import intake
import priority_customer as pc
from pathlib import Path


def test_fr5184_harvest_repos_come_from_saved_topic_set(tmp_path, monkeypatch):
    tagged = {"simonbarnett/hrsmith", "simonbarnett/ce-priority"}
    monkeypatch.setattr(pc, "load_topic_repos", lambda _home: tagged)
    monkeypatch.setattr(
        pc,
        "refresh_topic_repos",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected refresh")),
    )

    repos = intake.priority_customer_harvest_repos(home=tmp_path)

    assert repos == tagged
    assert intake.is_priority_customer_harvest_repo("SimonBarnett/hrsmith", home=tmp_path)
    assert intake.is_priority_customer_harvest_repo("SimonBarnett/ce-priority", home=tmp_path)
    assert not intake.is_priority_customer_harvest_repo("SimonBarnett/not-tagged", home=tmp_path)


def test_fr5184_empty_topic_cache_falls_back_to_topic_search(tmp_path, monkeypatch):
    calls = []
    fetch_json = lambda _url: {"items": [{"full_name": "SimonBarnett/new-customer"}]}

    def refresh(home, *, fetch_json=None):
        calls.append((home, fetch_json))
        return {"simonbarnett/new-customer"}

    monkeypatch.setattr(pc, "load_topic_repos", lambda _home: set())
    monkeypatch.setattr(pc, "refresh_topic_repos", refresh)

    repos = intake.priority_customer_harvest_repos(
        home=tmp_path,
        fetch_json=fetch_json,
    )

    assert repos == {"simonbarnett/new-customer"}
    assert calls == [(tmp_path, fetch_json)]
    assert intake.is_priority_customer_harvest_repo(
        "SimonBarnett/new-customer", home=tmp_path
    )


def test_fr5184_intake_has_no_hardcoded_priority_customer_list():
    text = Path(intake.__file__).read_text(encoding="utf-8")

    assert "PRIORITY_CUSTOMER_HARVEST_REPOS = frozenset" not in text
    assert '"simonbarnett/euroflo"' not in text
    assert '"simonbarnett/lynton"' not in text
    assert '"simonbarnett/trutex"' not in text
    assert '"simonbarnett/rees"' not in text
