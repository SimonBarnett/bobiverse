"""Hostile pins for FR #3146 / MRB #3148 — discover_repos unions focus.repos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

COMMON = REPO / "common" / "scripts"
sys.path.insert(0, str(COMMON))

import chair_health as ch  # noqa: E402


def test_hostile_focus_short_key_expands_and_discover_unions(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    focus = {
        "v": 1,
        "strict": True,
        "items": {},
        "repos": {"a-search": {"priority": 1, "label": "high"}},
    }
    (tmp_path / "focus.json").write_text(json.dumps(focus), encoding="utf-8")
    (tmp_path / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    got = ch.discover_repos(tmp_path, {"simonbarnett"}, lambda u: [], ignored=[])
    assert got == ["SimonBarnett/a-search"]


def test_hostile_product_files_and_skill_mention_fr3146():
    assert (REPO / "jeeves" / "tools" / "monitor" / "github_resync_focus.py").is_file()
    assert (REPO / "jeeves" / "scripts" / "Test-JeevesMonitorGithubResyncFocus.ps1").is_file()
    skill = (REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #3146" in skill
    assert "Test-JeevesMonitorGithubResyncFocus" in skill
    assert "discover_repos" in (REPO / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    src = (REPO / "common" / "scripts" / "chair_health.py").read_text(encoding="utf-8")
    assert "focus_repos" in src
    assert "focus_repos" in src and "FR #3146" in src

