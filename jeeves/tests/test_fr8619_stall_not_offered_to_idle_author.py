"""FR #8619: self-review stall FR must not be offered/assigned to idle author.

Regression after #8618 was handed to redqueen-7276 (named in idle[]).
Covers: assign_row refuse, queue-body truncate preserving stall_idle pin,
and seat_blocked reading that pin.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import gitclaim


def _stall_issue_body(idle: list[str], waiting: list[str]) -> str:
    # Long enough to exceed QUEUE_BODY_LIMIT (500) so truncate path runs.
    pad = "x" * 400
    idle_json = ",\n    ".join(f'"{n}"' for n in idle)
    wait_json = ",\n    ".join(f'"{w}"' for w in waiting)
    return (
        "<!-- stall-fp:stall:self-review-deadlock -->\n"
        "fingerprint=`stall:self-review-deadlock`\n"
        f"pad={pad}\n"
        "## Evidence\n"
        "```json\n"
        "{\n"
        f'  "idle": [\n    {idle_json}\n  ],\n'
        f'  "waiting": [\n    {wait_json}\n  ]\n'
        "}\n"
        "```\n"
        "---\n_via-intake FR=#5164_\n"
    )


def test_fr8619_body_for_queue_preserves_stall_idle_when_truncated():
    body = _stall_issue_body(
        ["redqueen-7276"],
        ["SimonBarnett/skills-visionary#111", "SimonBarnett/skills-visionary#112"],
    )
    assert len(body) > gitclaim.QUEUE_BODY_LIMIT
    queued = gitclaim._body_for_queue(body)
    assert "stall_idle:" in queued
    assert "redqueen-7276" in queued
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8618",
        "title": (
            "stall:self-review-deadlock:"
            "SimonBarnett/skills-visionary#111,SimonBarnett/skills-visionary#112"
        ),
        "body": queued,
    }
    assert gitclaim.seat_blocked_for_self_review_stall(row, "redqueen-7276") is True
    assert gitclaim.seat_blocked_for_self_review_stall(row, "redqueen-11048") is False


def _assign(home: Path, nick: str):
    # Mock stall_receipt skip so this test isolates the idle-author gate
    # (production still skips stall titles via row_skip_fr_reason).
    with mock.patch.object(
        gitclaim, "live_seat_nicks", return_value={"redqueen-7276", "redqueen-11048"}
    ), mock.patch.object(
        gitclaim, "free_seat_nicks", side_effect=lambda h, live: set(live)
    ), mock.patch.object(
        gitclaim, "worker_working_on", return_value=""
    ), mock.patch.object(
        gitclaim, "seat_open_job", return_value=""
    ), mock.patch.object(
        gitclaim, "worker_shop_channel", return_value="#redqueen"
    ), mock.patch.object(
        gitclaim, "_seat_model_allows_row", return_value=True
    ), mock.patch.object(
        gitclaim, "row_skip_fr_reason", return_value=None
    ):
        return gitclaim.assign_row(
            home,
            nick,
            "SimonBarnett/bobiverse",
            "FR",
            "8618",
            now=1_700_000_000.0,
            issue_open=lambda *a, **k: True,
            is_pull=lambda *a, **k: False,
            pr_exists=lambda *a, **k: True,
        )


def test_fr8619_assign_row_refuses_idle_author(tmp_path: Path):
    home = tmp_path
    body = (
        '{"idle": ["redqueen-7276"], '
        '"waiting": ["SimonBarnett/skills-visionary#111"]}'
    )
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#8618",
        "title": (
            "stall:self-review-deadlock:"
            "SimonBarnett/skills-visionary#111"
        ),
        "body": body,
        "url": "https://github.com/SimonBarnett/bobiverse/issues/8618",
    }
    (home / "queue.json").write_text(
        json.dumps(
            {
                "unaccepted": [row],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    assert gitclaim.seat_blocked_for_self_review_stall(row, "redqueen-7276") is True
    assert gitclaim.seat_blocked_for_self_review_stall(row, "redqueen-11048") is False

    st, detail = _assign(home, "redqueen-7276")
    assert st == "refused"
    assert "idle author" in str(detail).lower() or "self-review" in str(detail).lower()

    st2, detail2 = _assign(home, "redqueen-11048")
    assert st2 == "ok", detail2
