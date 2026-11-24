# -*- coding: utf-8 -*-
"""FR #9548: !assign must not depends-unresolved when unheld fr-digest is absent from queue.

Class of #9403/#9259: Depends-on lines with trailing annotation tokens
(``Depends-on: #9259 Digest: BOB-TRAY-UI`` without parentheses) tripped BOB-D5
``depends-unresolved`` via ``_row_depends_on_has_bad_ref`` before G1 could soft-allow
the live unheld fr-digest (same gap as #9418/#9455 for clean ``#N`` stamps).
"""
from __future__ import annotations

from pathlib import Path

import bobreport
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
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {
            "nick": "flamingo-17068",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-24T10:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _child(body: str, *, num: int = 9403) -> dict:
    return {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": 1,
        "ts": "2026-11-24T10:00:00Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": "BOB-TRAY-UI-11",
        "state": "open",
        "body": body,
        "labels": ["feature-request"],
        "event": "issues",
    }


def _fetch_factory(payload_by_id: dict[str, dict]):
    def fetch_issue(repo: str, num: str):
        assert repo.lower() == REPO.lower()
        return payload_by_id.get(str(num).lstrip("#"))

    return fetch_issue


def _digest_payload(*, held: bool = False) -> dict:
    labels = [{"name": "fr-digest"}, {"name": "feature-request"}]
    if held:
        labels.append({"name": "hold"})
    return {
        "state": "open",
        "title": "Digest: BOB-TRAY-UI",
        "body": "Kind: fr-digest\n",
        "labels": labels,
    }


def test_fr9548_bad_ref_ignores_annotation_junk_when_valid_ref_present():
    """Trailing bare annotation tokens must not trip D5 when #N is present."""
    row = _child("Depends-on: #9259 Digest: BOB-TRAY-UI\n")
    assert gitclaim._row_depends_on_has_bad_ref(row) is False
    assert gitclaim._row_depends_on_issue_refs(row) == [
        ("simonbarnett/bobiverse", 9259)
    ]
    row2 = _child("Depends-on: #9259, see digest\n")
    assert gitclaim._row_depends_on_has_bad_ref(row2) is False


def test_fr9548_bad_ref_still_fails_closed_on_only_junk():
    row = _child("Depends-on: soon\n")
    assert gitclaim._row_depends_on_has_bad_ref(row) is True
    why = gitclaim.depends_gate_reason(
        row,
        {"unaccepted": [row], "accepted": [], "done": []},
        open_keys=set(),
        issue_open=lambda *_a, **_k: False,
        issue_fetch=lambda *_a, **_k: None,
    )
    assert why == gitclaim.DEPENDS_UNRESOLVED_REASON


def test_fr9548_gate_allows_annotated_unheld_digest_absent_from_queue():
    child = _child("**Depends-on:** #9259 Digest: BOB-TRAY-UI\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    fetch = _fetch_factory({"9259": _digest_payload()})
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=set(),
        issue_open=lambda r, n: str(n).lstrip("#") == "9259",
        issue_fetch=fetch,
    )
    assert why is None


def test_fr9548_gate_held_annotated_digest_is_depends_held():
    child = _child("Depends-on: #9259 Digest: BOB-TRAY-UI\n")
    doc = {"unaccepted": [child], "accepted": [], "done": []}
    fetch = _fetch_factory({"9259": _digest_payload(held=True)})
    why = gitclaim.depends_gate_reason(
        child,
        doc,
        open_keys=set(),
        issue_open=lambda *_a, **_k: True,
        issue_fetch=fetch,
    )
    assert why == gitclaim.DEPENDS_HELD_REASON


def test_fr9548_assign_annotated_digest_absent_from_queue(home: Path):
    me = "flamingo-17068"
    child = _child("Depends-on: #9259 Digest: BOB-TRAY-UI\n")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [child], "accepted": [], "done": [], "workers": {}},
    )
    fetch = _fetch_factory({"9259": _digest_payload()})
    st, reason = gitclaim.assign_row(
        home,
        me,
        REPO,
        "FR",
        "9403",
        issue_open=lambda r, n: str(n).lstrip("#") in {"9259", "9403"},
        fetch_issue=fetch,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st == "ok", reason


def test_fr9548_marker_for_monitor():
    text = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "bob_g1_depends_annotation_soft" in text or "FR #9548" in text
