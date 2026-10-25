"""FR #4969: GitHub topic priority-customer is Jeeves low-priority (after all non-customer)."""
from __future__ import annotations

import json
import logging

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import priority_customer as pc


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    return tmp_path


def _row(repo, task="FR", num=1, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": num,
        "line": "x",
        "title": f"t{num}",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []})


def test_customer_unfocused_sorts_after_non_customer(_home):
    pc.save_topic_repos(_home, ["acme/cust"])
    rows = [_row("acme/cust", num=1), _row("acme/core", num=2)]
    _queue(_home, rows)
    ordered = gitclaim.ordered_unaccepted(_home)
    assert [r["repo"] for r in ordered] == ["acme/core", "acme/cust"]
    k_core = fi.offer_sort_key(_home, _row("acme/core", num=2))
    k_cust = fi.offer_sort_key(_home, _row("acme/cust", num=1))
    assert k_core < k_cust


def test_customer_focused_same_priority_sorts_after_non_customer(_home):
    pc.save_topic_repos(_home, ["acme/cust"])
    fi.handle_focus_cmd(_home, "high acme/core")
    fi.handle_focus_cmd(_home, "high acme/cust")
    _queue(_home, [_row("acme/cust", num=1), _row("acme/core", num=2)])
    assert [r["repo"] for r in gitclaim.ordered_unaccepted(_home)] == ["acme/core", "acme/cust"]


def test_without_topic_order_unchanged(_home):
    _queue(_home, [_row("acme/z", num=9), _row("acme/a", num=3)])
    ordered = [r["repo"] for r in gitclaim.ordered_unaccepted(_home)]
    assert ordered == ["acme/a", "acme/z"]


def test_explicit_item_focus_on_customer_still_wins(_home):
    pc.save_topic_repos(_home, ["acme/cust"])
    fi.handle_focus_cmd(_home, "acme/cust#1")
    _queue(_home, [_row("acme/cust", num=1), _row("acme/core", num=2)])
    assert gitclaim.ordered_unaccepted(_home)[0]["repo"] == "acme/cust"


def test_refresh_search_updates_persist_and_removal(_home):
    calls = []

    def fetch(url):
        calls.append(url)
        assert "topic:priority-customer" in url
        assert "rees" not in url and "trutex" not in url
        return {"items": [{"full_name": "acme/tagged"}]}

    out = pc.refresh_topic_repos(_home, fetch_json=fetch)
    assert out == {"acme/tagged"}
    assert pc.is_priority_customer(_home, "acme/tagged")
    assert not pc.is_priority_customer(_home, "acme/other")
    assert len(calls) == 1

    def fetch2(url):
        return {"items": []}

    pc.refresh_topic_repos(_home, fetch_json=fetch2)
    assert not pc.is_priority_customer(_home, "acme/tagged")


def test_refresh_failure_keeps_last_set(_home, caplog):
    pc.save_topic_repos(_home, ["acme/keep"])

    def boom(url):
        raise TimeoutError("rate")

    caplog.set_level(logging.WARNING)
    kept = pc.refresh_topic_repos(_home, fetch_json=boom)
    assert kept == {"acme/keep"}
    assert pc.is_priority_customer(_home, "acme/keep")
    assert any("priority-customer" in r.message for r in caplog.records)


def test_resync_calls_topic_search_once(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), {"v": 1, "unaccepted": [], "accepted": []})
    urls = []

    def fetch(url):
        urls.append(url)
        if "search/repositories" in url:
            return {"items": [{"full_name": "acme/cust"}]}
        if "/issues" in url:
            return []
        if "/pulls" in url:
            return []
        return []

    gitclaim.resync_from_github(tmp_path, ["acme/core"], fetch_json=fetch)
    searches = [u for u in urls if "search/repositories" in u and "priority-customer" in u]
    assert len(searches) == 1
    assert pc.is_priority_customer(tmp_path, "acme/cust")


def test_no_hardcoded_customer_repo_names():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    blob = ""
    for rel in (
        "common/scripts/priority_customer.py",
    ):
        p = root / rel
        if p.is_file():
            blob += p.read_text(encoding="utf-8")
    low = blob.lower()
    for name in ("rees", "trutex", "euroflo"):
        assert name not in low
    assert "ce-priority" not in low


def test_docs_say_how_to_tag():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    chair = (root / "common" / "scripts" / "chair_commands.py").read_text(encoding="utf-8")
    docs = (root / "jeeves" / "docs" / "jeeves-commands.md").read_text(encoding="utf-8")
    skill = (root / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    needle = "gh repo edit"
    topic = "priority-customer"
    assert topic in chair and topic in docs and topic in skill
    assert needle in chair or needle in docs
    assert needle in docs
