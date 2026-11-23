"""FR #9082: hold / on-hold are issues-only; never stamp on PRs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from repo_layout import REPO

sys.path.insert(0, str(REPO / "jeeves" / "tools" / "monitor"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import gitclaim  # noqa: E402
import intake  # noqa: E402
import pr_hold_labels  # noqa: E402


def test_fr9082_pr_hold_reason_ignores_hold_labels():
    assert gitclaim.pr_hold_reason(title="x", body="", labels=("hold", "on-hold")) is None
    assert gitclaim.pr_hold_reason(title="x", body="", labels=("do-not-merge",))
    assert gitclaim.fr_hold_reason(title="x", body="", labels=("hold",))


def test_fr9082_strip_and_forbidden():
    assert gitclaim.strip_issues_only_hold_labels(["via-intake", "hold", "harvest-lesson"]) == [
        "via-intake",
        "harvest-lesson",
    ]
    assert gitclaim.pr_forbidden_hold_labels(["Hold", "wip"]) == ["hold"]


def test_fr9082_filer_create_pr_strips_hold(monkeypatch):
    seen = {}

    class Fake:
        def create_pr(self, repo, title, body, branch, files, labels):
            seen["labels"] = list(labels)
            return {"url": "https://example/pr/1", "number": 1}

    out = intake._filer_create_pr(
        Fake(),
        "SimonBarnett/bobiverse",
        "lesson(harvest): x",
        "body",
        "intake/x",
        [{"path": "a", "content": "b"}],
        ["via-intake", "harvest-lesson", "hold", "on-hold"],
        draft=False,
    )
    assert out["number"] == 1
    assert "hold" not in seen["labels"]
    assert "on-hold" not in seen["labels"]
    assert "harvest-lesson" in seen["labels"]


def test_fr9082_monitor_exits_1_on_pr_hold(tmp_path, monkeypatch):
    fixture = tmp_path / "prs.json"
    fixture.write_text(
        json.dumps(
            {
                "repo": "SimonBarnett/bobiverse",
                "pulls": [
                    {
                        "number": 8757,
                        "state": "open",
                        "draft": False,
                        "title": "lesson",
                        "labels": [{"name": "harvest-lesson"}, {"name": "hold"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_PR_HOLD_LABELS_FIXTURE", str(fixture))
    from types import SimpleNamespace

    payload, code = pr_hold_labels.check(SimpleNamespace(dry_run=False))
    assert code == 1
    assert payload["ok"] is False
    assert payload["bad"]


def test_fr9082_monitor_ok_without_hold(tmp_path, monkeypatch):
    fixture = tmp_path / "prs.json"
    fixture.write_text(
        json.dumps(
            {
                "repo": "SimonBarnett/bobiverse",
                "pulls": [
                    {
                        "number": 1,
                        "state": "open",
                        "labels": [{"name": "harvest-lesson"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEEVES_PR_HOLD_LABELS_FIXTURE", str(fixture))
    from types import SimpleNamespace

    payload, code = pr_hold_labels.check(SimpleNamespace(dry_run=False))
    assert code == 0
    assert payload["ok"] is True
