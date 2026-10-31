"""FR #5184: harvest customer set comes from priority-customer topic, not a hardcoded list."""
from __future__ import annotations

from pathlib import Path

import intake
import priority_customer as pc


def test_topic_repo_is_customer_harvest_repo(tmp_path):
    pc.save_topic_repos(tmp_path, ["SimonBarnett/hrsmith", "SimonBarnett/ce-priority"])
    got = intake.harvest_priority_customer_repos(home=tmp_path)
    assert "simonbarnett/hrsmith" in got
    assert "simonbarnett/ce-priority" in got


def test_repo_without_topic_is_not_customer_harvest_repo(tmp_path):
    pc.save_topic_repos(tmp_path, ["SimonBarnett/hrsmith"])
    got = intake.harvest_priority_customer_repos(home=tmp_path)
    assert "simonbarnett/bobiverse" not in got
    assert "simonbarnett/agentic_fomprep" not in got


def test_empty_topic_file_falls_back_to_search_not_hardcoded(tmp_path):
    def fetch(_url: str):
        return {
            "items": [
                {"full_name": "SimonBarnett/hrsmith"},
                {"full_name": "SimonBarnett/ce-priority"},
            ]
        }

    got = intake.harvest_priority_customer_repos(home=tmp_path, fetch_json=fetch)
    assert "simonbarnett/hrsmith" in got
    assert "simonbarnett/ce-priority" in got
    assert "simonbarnett/euroflo" not in got


def test_missing_file_uses_module_search(tmp_path, monkeypatch):
    def fake(url: str):
        assert "priority-customer" in url
        return {"items": [{"full_name": "SimonBarnett/hrsmith"}]}

    monkeypatch.setattr(pc, "github_topic_fetch", fake)
    got = intake.harvest_priority_customer_repos(home=tmp_path)
    assert "simonbarnett/hrsmith" in got
    assert "simonbarnett/euroflo" not in got


def test_intake_has_no_hardcoded_harvest_repo_list():
    text = Path(intake.__file__).read_text(encoding="utf-8")
    assert "PRIORITY_CUSTOMER_HARVEST_REPOS = frozenset" not in text
    start = text.index("def harvest_priority_customer_repos")
    nxt = text.find("\ndef ", start + 1)
    block = text[start:nxt].lower()
    for slug in ("euroflo", "lynton", "trutex", "rees", "hrsmith", "ce-priority"):
        assert slug not in block, slug
