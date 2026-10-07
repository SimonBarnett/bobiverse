"""FR #3146: github_resync_focus monitor finding when focus starves the queue."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from repo_layout import REPO

MON = REPO / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import github_resync_focus as grf  # noqa: E402


def test_module_and_wrapper_exist():
    root = REPO / "jeeves"
    assert (root / "tools" / "monitor" / "github_resync_focus.py").is_file()
    assert (root / "scripts" / "Test-JeevesMonitorGithubResyncFocus.ps1").is_file()
    text = (root / "scripts" / "Invoke-JeevesMonitorCheck.ps1").read_text(encoding="utf-8-sig")
    assert "github_resync_focus" in text


def test_finding_when_focus_set_queue_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("JEEVES_RESYNC_REPOS", raising=False)
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    focus = {
        "v": 1,
        "repos": {"a-search": {"priority": 1}},
        "items": {},
        "strict": True,
    }
    (tmp_path / "focus.json").write_text(json.dumps(focus), encoding="utf-8")
    (tmp_path / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home=str(tmp_path), dry_run=False)
    payload, code = grf.check(args)
    assert code == 1
    assert payload["ok"] is False
    assert payload["focus_repo_count"] == 1
    assert "SimonBarnett/a-search" in (payload.get("discover_repos") or [])
    assert payload["findings"]


def test_ok_when_no_focus(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_DIGEST_HOME", raising=False)
    (tmp_path / "focus.json").write_text(
        json.dumps({"v": 1, "repos": {}, "items": {}, "strict": False}), encoding="utf-8"
    )
    (tmp_path / "queue.json").write_text(
        json.dumps({"unaccepted": [], "accepted": []}), encoding="utf-8"
    )
    args = SimpleNamespace(chair_home=str(tmp_path), digest_home=str(tmp_path), dry_run=False)
    payload, code = grf.check(args)
    assert code == 0
    assert payload["ok"] is True
