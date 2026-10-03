"""FR #1080 / PR #1122 / PR #1174: needs-mrb1 must not strand the offer queue.

#1122 skipped needs-mrb1 as FR (GIVEUP playbook). Under focus.strict that emptied
bobiverse offers (#1174). Chair now offers needs-mrb1 FRs; workers still GIVEUP.
Corrupt require_machine=mrb1 remains rejected. Strict fallback stays in-focus.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import gitclaim


def test_needs_mrb1_is_offerable_not_require_machine():
    assert "needs-mrb1" not in gitclaim.SKIP_FR_LABELS
    assert gitclaim.issue_skip_fr_reason(title="FR: something", labels=("needs-mrb1", "via-intake")) is None
    assert gitclaim.infer_require_machine(labels=["needs-mrb1", "feature-request"]) in (None, "")
    assert gitclaim.infer_require_machine(labels=["needs-ionos"]) == "ionos"
    # Corrupt stamp ignored
    row = {"require_machine": "mrb1", "labels": ["feature-request"], "title": "x", "body": "", "task": "FR"}
    assert not gitclaim.row_require_machine(row)
    assert gitclaim.fr_row_offerable(
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#1055",
            "title": "FR: something",
            "labels": ["needs-mrb1", "feature-request"],
            "state": "open",
            "body": "",
        }
    )


def test_row_on_cooldown_is_per_giveup_seat():
    now = time.time()
    until = datetime.fromtimestamp(now + 600, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {"cooldown_until": until, "giveup_seats": "marchhare-1"}
    assert gitclaim.row_on_cooldown(row, now, "marchhare-1") is True
    assert gitclaim.row_on_cooldown(row, now, "marchhare-2") is False
    assert gitclaim.row_on_cooldown(row, now, "") is True


def test_offer_focus_strict_does_not_leak_out_of_focus(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    # Focus only bobiverse; offerable row is Club-Madeira (out of focus).
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
