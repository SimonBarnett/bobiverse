"""FR #3146: discover_repos unions focus.repos (short keys → Owner/name)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

COMMON = REPO / "common" / "scripts"
sys.path.insert(0, str(COMMON))

import chair_health as ch  # noqa: E402
import focus_ignore  # noqa: E402


def _write_focus(home: Path, repos) -> None:
    home.mkdir(parents=True, exist_ok=True)
    if isinstance(repos, list):
        body = {"v": 1, "repos": {r: {"priority": 1} for r in repos}, "items": {}, "strict": True}
    else:
        body = {"v": 1, "repos": repos, "items": {}, "strict": True}
    (home / "focus.json").write_text(json.dumps(body), encoding="utf-8")


def test_focus_repos_expands_short_key(tmp_path):
    _write_focus(tmp_path, ["a-search", "SimonBarnett/bobiverse"])
    got = ch.focus_repos(tmp_path, {"simonbarnett"})
    assert "SimonBarnett/a-search" in got
    assert "SimonBarnett/bobiverse" in got


def test_discover_repos_unions_focus_when_queue_and_config_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    _write_focus(tmp_path, {"a-search": {"priority": 1}})
    (tmp_path / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )

    def getter(url):
        # Empty /user/repos → old path would return [] and note=no repos.
        return []

    got = ch.discover_repos(tmp_path, {"simonbarnett"}, getter, ignored=[])
    assert got == ["SimonBarnett/a-search"]


def test_discover_repos_unions_focus_even_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("JEEVES_RESYNC_REPOS", "SimonBarnett/bobiverse")
    _write_focus(tmp_path, ["a-search"])
    got = ch.discover_repos(tmp_path, {"simonbarnett"}, lambda u: [], ignored=[])
    assert "SimonBarnett/bobiverse" in got
    assert "SimonBarnett/a-search" in got


def test_discover_repos_skips_ignored_focus(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    _write_focus(tmp_path, ["a-search", "bobiverse"])
    got = ch.discover_repos(tmp_path, {"simonbarnett"}, lambda u: [], ignored=["a-search"])
    assert "SimonBarnett/a-search" not in got
    assert "SimonBarnett/bobiverse" in got


def test_resync_cycle_no_longer_no_repos_when_focus_set(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    _write_focus(tmp_path, ["a-search"])
    (tmp_path / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    calls = []

    def fetch(url, **kw):
        calls.append(url)
        if "/issues" in url:
            return []
        return []

    # Avoid real GitHub; stub resync_from_github via monkeypatch on gitclaim after import.
    import gitclaim

    def fake_resync(home, repos, **kw):
        return {"ok": True, "unaccepted": 0, "added": 0, "dropped": 0, "repos": list(repos), "failed": []}

    monkeypatch.setattr(gitclaim, "resync_from_github", fake_resync)
    monkeypatch.setattr(gitclaim, "prune_unassignable_queue", lambda home: {"dropped": 0})
    out = ch.resync_cycle(tmp_path, token="x", ignored=[], fetch_json=fetch, owners={"simonbarnett"})
    assert out.get("note") != "no repos"
    assert "SimonBarnett/a-search" in (out.get("repos") or [])
