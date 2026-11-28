# -*- coding: utf-8 -*-
"""FR #9434: stuck/report G1 must pass issue_fetch when digests are absent from queue.

Class of live #9259/#9261 after #9420: offer paths had FR #9418 issue_fetch, but
stuck_job_sweep.classify_queue_row and stall_detectors still called
row_depends_open_reason with issue_open only → depends_on_open on the report.
Also Depends-on annotations like ``#9259 (Digest: BOB-TRAY-UI)`` must not be
depends-unresolved (BOB-D5).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gitclaim
import stall_detectors as sd
import stuck_job_sweep as sweep


REPO = "SimonBarnett/bobiverse"


def _old_ts(now: float, age_s: float = 3600.0) -> str:
    return datetime.fromtimestamp(now - age_s, tz=timezone.utc).isoformat()


def _fr(*, num: int, ts: str, body: str, title: str = "child", labels=None) -> dict:
    return {
        "task": "FR",
        "repo": REPO,
        "id": f"#{num}",
        "ident": str(num),
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": title,
        "body": body,
        "ts": ts,
        "labels": labels or ["feature-request"],
        "event": "issues",
        "line": f"FR {REPO}#{num}",
    }


def _fetch_factory(payload_by_id: dict[str, dict]):
    def fetch_issue(repo: str, num: str):
        assert repo.lower() == REPO.lower()
        return payload_by_id.get(str(num).lstrip("#"))

    return fetch_issue


def test_fr9434_depends_annotation_not_unresolved():
    """``Depends-on: #9259 (Digest: BOB-TRAY-UI)`` is a valid relative ref + note."""
    row = _fr(
        num=9403,
        ts=_old_ts(1_700_000_000.0),
        body="**Depends-on:** #9259 (Digest: BOB-TRAY-UI)\n",
        title="BOB-TRAY-UI-11",
    )
    assert gitclaim._row_depends_on_has_bad_ref(row) is False
    assert gitclaim._row_depends_on_issue_refs(row) == [
        (REPO.lower(), 9259),
    ]
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "fr-digest"}, {"name": "feature-request"}],
            }
        }
    )
    why = gitclaim.row_depends_open_reason(
        row,
        set(),
        issue_open=lambda r, n: True,
        doc={"unaccepted": [row], "accepted": []},
        issue_fetch=fetch,
    )
    # FR #10059: an unheld OPEN digest still blocks. Annotation must not
    # turn that into depends-unresolved.
    assert why == gitclaim.DEPENDS_OPEN_REASON


def test_fr9434_classify_unheld_digest_absent_not_depends_on_open(
    tmp_path: Path, monkeypatch
):
    """FR #10059: unheld OPEN digest is depends_on_open for stuck classify."""
    now = 1_700_000_000.0
    home = tmp_path
    child = _fr(
        num=9261,
        ts=_old_ts(now, 4000),
        body="**Depends-on:** #9259\n",
        title="BOB-TRAY-UI-01",
    )
    # Digest deliberately absent from queue (go-gate not implementation work).
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": []},
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_open_checker",
        lambda issue_open=None: (lambda repo, num: str(num).lstrip("#") == "9259"),
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_fetch_checker",
        lambda fetch_issue=None: _fetch_factory(
            {
                "9259": {
                    "state": "open",
                    "title": "Digest: BOB-TRAY-UI",
                    "body": "Kind: fr-digest\n",
                    "labels": [
                        {"name": "fr-digest"},
                        {"name": "feature-request"},
                    ],
                }
            }
        ),
    )
    info = sweep.classify_queue_row(
        child,
        bucket="unaccepted",
        now=now,
        live={"redqueen-1"},
        idle={"redqueen-1"},
        home=home,
    )
    # FR #10059: unheld OPEN digest is depends_on_open, not held or unresolved.
    assert info.get("rule") == "depends_on_open"
    assert info.get("rule") != "depends_held"
    assert info.get("rule") != "depends_unresolved"
    # G1-ok child may still look starved while an eligible seat is idle — that
    # is correct; it must not be mis-labeled depends_on_open.
    assert info.get("state") in ("unaccepted", "held")


def test_fr9434_classify_without_fetch_still_depends_on_open_regression(
    tmp_path: Path, monkeypatch
):
    """If issue_fetch is unavailable, live OPEN non-digest still depends_on_open."""
    now = 1_700_000_000.0
    home = tmp_path
    child = _fr(
        num=9261,
        ts=_old_ts(now, 4000),
        body="**Depends-on:** #9259\n",
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": []},
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_open_checker",
        lambda issue_open=None: (lambda repo, num: True),
    )
    monkeypatch.setattr(
        gitclaim,
        "depends_issue_fetch_checker",
        lambda fetch_issue=None: (_ for _ in ()).throw(RuntimeError("no fetch")),
    )
    info = sweep.classify_queue_row(
        child,
        bucket="unaccepted",
        now=now,
        live={"redqueen-1"},
        idle={"redqueen-1"},
        home=home,
    )
    assert info["state"] == "held"
    assert info["rule"] == "depends_on_open"


def test_fr9434_stall_idle_with_work_sees_g1_ok_child():
    """FR #10059: unheld OPEN digest blocks, so idle_with_work does not fire."""
    now = 1_700_000_000.0
    child = _fr(
        num=9261,
        ts=_old_ts(now, 4000),
        body="**Depends-on:** #9259\n",
    )
    snap = {
        "now": now,
        "idle": ["flamingo-14096"],
        "unaccepted": [child],
        "accepted": [],
        "idle_with_work_s": 600.0,
        "depends_issue_open": lambda repo, num: True,
        "depends_issue_fetch": _fetch_factory(
            {
                "9259": {
                    "state": "open",
                    "title": "Digest",
                    "body": "",
                    "labels": [{"name": "fr-digest"}],
                }
            }
        ),
    }
    found = sd.detect_idle_with_work(snap)
    assert found == []


def test_fr9434_stall_idle_with_work_still_skips_plain_open_depend():
    """issue_fetch must not unblock an ordinary OPEN Depends-on (non-digest)."""
    now = 1_700_000_000.0
    child = _fr(
        num=9261,
        ts=_old_ts(now, 4000),
        body="**Depends-on:** #9259\n",
    )
    snap = {
        "now": now,
        "idle": ["flamingo-14096"],
        "unaccepted": [child],
        "accepted": [],
        "idle_with_work_s": 600.0,
        "depends_issue_open": lambda repo, num: True,
        "depends_issue_fetch": _fetch_factory(
            {
                "9259": {
                    "state": "open",
                    "title": "Ordinary FR",
                    "body": "ship it",
                    "labels": [{"name": "feature-request"}],
                }
            }
        ),
    }
    assert sd.detect_idle_with_work(snap) == []
