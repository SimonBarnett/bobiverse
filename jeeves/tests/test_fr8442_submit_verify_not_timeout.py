"""FR #8442: a live submit-verify is not an offer-timeout."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import bobreport
import gitclaim
import registered_machines


def test_fr8442_in_flight_paste_does_not_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {}
    digest["machines"]["flamingo"]["worker_list"] = [{
        "nick": "flamingo-22532",
        "state": "doing",
        "progress_phase": "submit-verify",
    }]
    bobreport.save_digest(tmp_path, digest)
    now = time.time()
    offered = (datetime.now(timezone.utc) - timedelta(seconds=gitclaim.OFFER_TIMEOUT_S + 30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "FIX",
        "id": "#8385",
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/8385",
        "offered_to": "flamingo-22532",
        "offered_ts": offered,
        "offered_count": 1,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    st, _job = gitclaim.offer_focus_top(tmp_path, "flamingo-22532", "#flamingo", now=now)
    held = gitclaim.load_unaccepted(tmp_path)[0]
    assert held.get("offered_to") == "flamingo-22532"
    assert int(held.get("offered_count") or 0) == 1
    assert not (held.get("offer_unanswered") or {})
    assert st in ("empty", "ok")
