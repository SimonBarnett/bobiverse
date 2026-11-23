"""FR #9347: digest/status surfaces held-pass (phase-gated MRB PASS) separately."""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import mrb_merge_on_green as mog


def test_fr9347_summarize_needs_human_recycle_hint():
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#8752",
            "number": "8752",
            "needs_human": True,
            "giveup_count": 2,
            "title": "walled",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/bobiverse#8752",
        }
    ]
    pub = bobreport.summarize_public_queue(rows, [])
    assert pub["needs_human_count"] == 1
    hint = str(pub.get("needs_human_hint") or "")
    assert "!cleargiveup" in hint
    assert "!recycle" in hint or "recycle" in hint.lower()


def test_fr9347_public_queue_held_pass_count(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1",
                    "number": "1",
                    "needs_human": True,
                    "title": "human",
                    "labels": ["feature-request"],
                    "line": "FR SimonBarnett/bobiverse#1",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    led = mog._empty_ledger()
    led["pending"] = [
        {
            "repo": "SimonBarnett/bobiverse",
            "pr": "8763",
            "pass_sha": "abc123",
            "status": "skip_hold",
            "hold_reason": "phase-gated",
            "url": "https://github.com/SimonBarnett/bobiverse/pull/8763",
        },
        {
            "repo": "SimonBarnett/bobiverse",
            "pr": "9000",
            "pass_sha": "def456",
            "status": "pending",
            "url": "https://github.com/SimonBarnett/bobiverse/pull/9000",
        },
    ]
    path = mog.ledger_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(led), encoding="utf-8")

    pub = bobreport._public_queue(tmp_path)
    assert pub["needs_human_count"] == 1
    assert int(pub.get("held_pass_count") or 0) == 1
    assert str(pub.get("needs_human_hint") or "").find("!cleargiveup") >= 0
