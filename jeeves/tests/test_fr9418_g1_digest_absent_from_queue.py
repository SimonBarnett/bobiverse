# -*- coding: utf-8 -*-
"""FR #9418: BOB-G1 when unheld fr-digest is OPEN on GitHub but absent from local queue.

Class of #9259/#9261: !assign refused depends-open because find_open_fr_row missed
the go-gate digest (not queued) while issue_open True fell through to BOB-D3.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines
import pytest


REPO = "SimonBarnett/bobiverse"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-23T18:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _child(**kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": "#9261",
        "seq": 1,
        "ts": "2026-11-23T18:00:00Z",
        "line": f"FR {REPO}#9261",
        "url": f"https://github.com/{REPO}/issues/9261",
        "title": "Child of digest",
        "state": "open",
        "body": "Depends-on: #9259\nImplement tray item.\n",
        "labels": ["feature-request"],
        "event": "issues",
    }
    r.update(kw)
    return r


def _issue_open_factory(open_ids: set[str]):
    def issue_open(repo: str, num: str) -> bool:
        assert repo.lower() == REPO.lower()
        return str(num).lstrip("#") in open_ids

    return issue_open


def _fetch_factory(payload_by_id: dict[str, dict]):
    def fetch_issue(repo: str, num: str):
        assert repo.lower() == REPO.lower()
        return payload_by_id.get(str(num).lstrip("#"))

    return fetch_issue


def test_row_depends_open_allows_unheld_digest_absent_from_queue():
    """Unit: live OPEN + fr-digest labels + no hold => not depends-open."""
    child = _child()
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "feature-request"}, {"name": "fr-digest"}],
            }
        }
    )
    why = gitclaim.row_depends_open_reason(
        child,
        set(),
        issue_open=_issue_open_factory({"9259"}),
        doc={"unaccepted": [child], "accepted": []},
        issue_fetch=fetch,
    )
    assert why is None


def test_row_depends_open_held_digest_absent_from_queue_is_depends_held():
    child = _child()
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: held",
                "body": "",
                "labels": [
                    {"name": "feature-request"},
                    {"name": "fr-digest"},
                    {"name": "hold"},
                ],
            }
        }
    )
    why = gitclaim.row_depends_open_reason(
        child,
        set(),
        issue_open=_issue_open_factory({"9259"}),
        doc={"unaccepted": [child], "accepted": []},
        issue_fetch=fetch,
    )
    assert why == gitclaim.DEPENDS_HELD_REASON


def test_row_depends_open_plain_open_depend_still_blocks():
    child = _child()
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Ordinary FR",
                "body": "ship it",
                "labels": [{"name": "feature-request"}],
            }
        }
    )
    why = gitclaim.row_depends_open_reason(
        child,
        set(),
        issue_open=_issue_open_factory({"9259"}),
        doc={"unaccepted": [child], "accepted": []},
        issue_fetch=fetch,
    )
    assert why == gitclaim.DEPENDS_OPEN_REASON


def test_offer_child_when_digest_open_unheld_not_queued(home: Path):
    """!bored offers #9261 when #9259 is OPEN fr-digest on GitHub but not queued."""
    me = "marchhare-35600"
    child = _child(seq=1)
    later = _child(
        id="#9999",
        seq=2,
        body="",
        title="unrelated",
        url=f"https://github.com/{REPO}/issues/9999",
        line=f"FR {REPO}#9999",
    )
    # Digest deliberately absent from unaccepted/accepted (go-gate not implementation).
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child, later], "accepted": [], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(home, REPO)

    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "",
                "labels": [{"name": "fr-digest"}, {"name": "feature-request"}],
            }
        }
    )
    st, job = gitclaim.offer_focus_top(
        home,
        me,
        "#marchhare",
        issue_open=_issue_open_factory({"9259", "9261", "9999"}),
        fetch_issue=fetch,
    )
    assert st == "ok" and job is not None
    assert job["id"] == "#9261"


def test_assign_child_when_digest_open_unheld_not_queued(home: Path):
    me = "marchhare-35600"
    child = _child()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": [], "workers": {}},
    )
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: BOB-TRAY-UI",
                "body": "Kind: fr-digest\n",
                "labels": [{"name": "feature-request"}, {"name": "fr-digest"}],
            }
        }
    )
    st, reason = gitclaim.assign_row(
        home,
        me,
        REPO,
        "FR",
        "9261",
        issue_open=_issue_open_factory({"9259", "9261"}),
        fetch_issue=fetch,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "ok", reason


def test_assign_refuses_depends_held_when_digest_held_not_queued(home: Path):
    me = "marchhare-35600"
    child = _child()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": [], "workers": {}},
    )
    fetch = _fetch_factory(
        {
            "9259": {
                "state": "open",
                "title": "Digest: held",
                "body": "",
                "labels": [
                    {"name": "fr-digest"},
                    {"name": "hold"},
                    {"name": "feature-request"},
                ],
            }
        }
    )
    st, reason = gitclaim.assign_row(
        home,
        me,
        REPO,
        "FR",
        "9261",
        issue_open=_issue_open_factory({"9259", "9261"}),
        fetch_issue=fetch,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "refused"
    assert "depends-held" in str(reason)


def test_fr9418_marker_for_monitor_soft_ok():
    text = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "bob_g1_skip_held_digest" in text
    assert "bob_g1_live_digest_absent_queue" in text