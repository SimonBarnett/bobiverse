"""FR #1080 / #1122 / PR #1236: needs-mrb1 is not SKIP_FR / not require_machine=mrb1.

Operator 2026-10-04: needs-mrb1 must not block offers (hallucination).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import gitclaim


def test_needs_mrb1_is_not_skip_but_not_require_machine():
    # PR #1236: SKIP_FR for needs-mrb1 emptied the bobiverse focus queue — do not SKIP_FR.
    assert "needs-mrb1" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: something", labels=("needs-mrb1", "via-intake")) is None
    assert gitclaim.infer_require_machine(labels=["needs-mrb1", "feature-request"]) in (None, "")
    assert gitclaim.infer_require_machine(labels=["needs-ionos"]) == "ionos"
    # Corrupt stamp ignored
    row = {"require_machine": "mrb1", "labels": ["feature-request"], "title": "x", "body": "", "task": "FR"}
    assert not gitclaim.row_require_machine(row)
    # Operator 2026-10-04: offer gate removed
    assert gitclaim.row_awaits_mrb1({"labels": ["needs-mrb1"]}) is False


def test_row_on_cooldown_is_per_giveup_seat():
    now = time.time()
    until = datetime.fromtimestamp(now + 600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {"cooldown_until": until, "giveup_seats": "marchhare-1"}
    assert gitclaim.row_on_cooldown(row, now, "marchhare-1") is True
    assert gitclaim.row_on_cooldown(row, now, "marchhare-2") is False
    assert gitclaim.row_on_cooldown(row, now, "") is True


def test_strict_focus_fallback_stays_inside_focused_repos(tmp_path, monkeypatch):
    """PR #1236: when focus.strict, do not leak Club-Madeira while focused on bobiverse."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":["SimonBarnett/bobiverse"],"strict":true}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/Club-Madeira",
                    "task": "FR",
                    "id": "#2",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/Club-Madeira#2",
                    "title": "FR: email after foundation",
                    "body": "Parent: #1",
                    "labels": ["feature-request"],
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    assert job is None


def test_strict_focus_fallback_offers_in_focus_when_order_misses(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":{"SimonBarnett/bobiverse":{"priority":1}},"strict":true}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1074",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#1074",
                    "title": "FR: sync timeout",
                    # FR #1363: needs-mrb1 is not offerable; use a clearable vision-free FR.
                    "labels": ["feature-request", "via-intake"],
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-1", "#win-mpre8vi4u6u")
    assert st == "ok"
    assert job["id"] == "#1074"


def test_strict_focus_offers_needs_mrb1_under_focus(tmp_path, monkeypatch):
    """Operator 2026-10-04: needs-mrb1 label must not block offers under strict focus."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    (home / "focus.json").write_text(
        '{"v":1,"repos":{"SimonBarnett/bobiverse":{"priority":1}},"strict":true}',
        encoding="utf-8",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": "#1074",
                    "seq": 1,
                    "ts": "t",
                    "line": "FR SimonBarnett/bobiverse#1074",
                    "title": "FR: sync timeout",
                    "labels": ["feature-request", "needs-mrb1"],
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "win-mpre8vi4u6u-1", "#win-mpre8vi4u6u")
    assert st == "ok"
    assert job["id"] == "#1074"
