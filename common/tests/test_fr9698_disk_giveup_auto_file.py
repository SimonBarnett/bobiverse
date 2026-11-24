"""FR #9698: disk GIVEUP/NACK auto-files one machine-pinned bobiverse issue."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import disk_starvation_chair_file as dsf  # noqa: E402


def test_is_disk_starvation_reason_tokens():
    assert dsf.is_disk_starvation_reason("worktree-create-failed:disk")
    assert dsf.is_disk_starvation_reason("worktree-create-failed:disk-low")
    assert dsf.is_disk_starvation_reason("reason=worktree-create-failed:disk-low (FR #6240)")
    assert dsf.is_disk_starvation_reason("disk-low")
    assert not dsf.is_disk_starvation_reason("worktree-create-failed:fetch")
    assert not dsf.is_disk_starvation_reason("busy")
    assert not dsf.is_disk_starvation_reason("")


def test_machine_from_seat_no_hardcode():
    assert dsf.machine_from_seat("flamingo-17160") == "flamingo"
    assert dsf.machine_from_seat("redqueen-11944") == "redqueen"
    assert dsf.machine_from_seat("") == ""


def test_issue_title_and_body_require_machine_line():
    title = dsf.issue_title("flamingo")
    assert title.startswith("flamingo:")
    assert "disk starvation" in title
    body = dsf.issue_body(
        machine="flamingo",
        nick="flamingo-17160",
        job="SimonBarnett/bobiverse FR 9688",
        reason="worktree-create-failed:disk-low",
        free_gb=4.8,
    )
    assert body.splitlines()[0] == "require_machine: flamingo"
    assert dsf.MARKER in body
    assert "flamingo-17160" in body
    assert "4.8" in body
    assert dsf.needs_machine_label("flamingo") == "needs-flamingo"


def test_ensure_creates_when_no_twin():
    created = {}

    def _create(title, body, labels=None):
        created["title"] = title
        created["body"] = body
        created["labels"] = labels
        return {"number": 9696}

    out = dsf.ensure_disk_starvation_issue(
        machine="flamingo",
        nick="flamingo-17160",
        job="SimonBarnett/bobiverse#9688",
        reason="worktree-create-failed:disk",
        list_open=lambda: [],
        create=_create,
    )
    assert out["ok"] is True
    assert out["action"] == "created"
    assert out["issue"] == 9696
    assert created["title"].startswith("flamingo:")
    assert created["body"].startswith("require_machine: flamingo")
    assert "needs-flamingo" in (created.get("labels") or [])


def test_ensure_comments_open_twin_no_second_file():
    comments = []
    creates = []

    twin = {
        "number": 9696,
        "title": "flamingo: disk starvation — worktree-create-failed:disk (auto)",
        "body": "require_machine: flamingo\n\nDisk starvation on flamingo",
        "state": "open",
    }

    out = dsf.ensure_disk_starvation_issue(
        machine="flamingo",
        nick="flamingo-17068",
        reason="disk-low",
        list_open=lambda: [twin],
        create=lambda *a, **k: creates.append(a) or {"number": 9999},
        comment=lambda n, t: comments.append((n, t)),
    )
    assert out["ok"] is True
    assert out["action"] == "twin_comment"
    assert out["issue"] == 9696
    assert creates == []
    assert comments and comments[0][0] == 9696


def test_maybe_file_from_giveup_skips_non_disk():
    assert (
        dsf.maybe_file_from_giveup(
            nick="flamingo-1",
            reason="busy",
            create=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no create")),
        )
        is None
    )


def test_maybe_file_from_giveup_disk_calls_ensure():
    out = dsf.maybe_file_from_giveup(
        nick="flamingo-17160",
        reason="worktree-create-failed:disk-low",
        repo="SimonBarnett/bobiverse",
        task="FR",
        ident="#9688",
        list_open=lambda: [],
        create=lambda title, body, labels=None: {"number": 42},
    )
    assert out is not None
    assert out["ok"] is True
    assert out["machine"] == "flamingo"
    assert out["action"] == "created"
