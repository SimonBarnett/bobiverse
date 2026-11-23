# -*- coding: utf-8 -*-
"""FR #9108 / BOB-G3: unheld digest is never offered; adjacent FR still offerable."""
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
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {
            "nick": "marchhare-35600",
            "state": "idle",
            "kind": "grok",
            "start_model": "grok-4",
            "configured_model": "grok-4",
            "updated": "2026-11-17T12:00:00Z",
        }
    ]
    bobreport.save_digest(tmp_path, digest)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [], "workers": {}},
    )
    return tmp_path


def _row(num: int, seq: int, **kw) -> dict:
    r = {
        "repo": REPO,
        "task": "FR",
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{num:02d}Z",
        "line": f"FR {REPO}#{num}",
        "url": f"https://github.com/{REPO}/issues/{num}",
        "title": f"FR {num}",
        "state": "open",
        "body": "Depends-on: (none)\n",
        "event": "issues",
        "labels": [],
    }
    r.update(kw)
    return r


def test_fr9108_unheld_digest_skipped_ordinary_offered(home: Path):
    me = "marchhare-35600"
    digest = _row(100, 1, labels=["digest"], title="Digest: batch")
    later = _row(101, 2, body="Depends-on: (none)\n", title="ordinary FR")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [digest, later], "accepted": [], "done": [], "workers": {}},
    )
    fi.handle_focus_cmd(home, REPO)
    st, job = gitclaim.offer_focus_top(home, me, "#marchhare")
    assert st == "ok" and job is not None
    assert job["id"] == "#101"
    doc = gitclaim.load_queue(home)
    row100 = next(r for r in doc["unaccepted"] if r.get("id") == "#100")
    assert not str(row100.get("offered_to") or "").strip()
    assert gitclaim.digest_issue_reason(row100)


def test_fr9108_assign_refuses_digest(home: Path):
    me = "marchhare-35600"
    digest = _row(200, 1, labels=["fr-digest"], title="Digest gate")
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [digest], "accepted": [], "done": [], "workers": {}},
    )
    st, detail = gitclaim.assign_row(home, me, REPO, "FR", "#200")
    assert st == "refused"
    assert "digest" in str(detail).lower()
