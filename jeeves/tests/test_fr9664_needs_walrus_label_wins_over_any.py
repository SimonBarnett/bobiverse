# -*- coding: utf-8 -*-
"""FR #9664: needs-walrus label wins over require_machine=any (no wrong-shop offer loop)."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-11-24T12:00:00Z",
            }
            for pid in workers
        ]
    bobreport.save_digest(home, doc)


def _row_needs_walrus_any():
    return {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#9664",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#9664",
        "title": "chair: needs-walrus label left require_machine=any",
        # No Depends-on / needs_human: those gates empty every shop (including walrus).
        # This pin is the needs-walrus vs rm=any thrash (#9622 evidence class).
        "body": "exact-seat / needs-walrus offer gate\n",
        "labels": ["feature-request", "via-intake", "needs-walrus"],
        "state": "open",
        "require_machine": "any",
        "require_machine_operator": True,
    }


def test_fr9664_row_require_machine_label_wins_over_operator_any():
    row = _row_needs_walrus_any()
    assert gitclaim.row_require_machine(row) == "walrus"
    assert gitclaim.row_blocked_for_machine(row, "redqueen-10704")
    assert gitclaim.row_blocked_for_machine(row, "flamingo-17160")
    assert not gitclaim.row_blocked_for_machine(row, "walrus-1")


def test_fr9664_stamp_rewrites_any_to_walrus_from_label():
    row = _row_needs_walrus_any()
    gitclaim._stamp_require_machine(row)
    assert row.get("require_machine") == "walrus"
    assert gitclaim.row_require_machine(row) == "walrus"


def test_fr9664_offer_skips_redqueen_and_flamingo(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"walrus": [1], "redqueen": [10704], "flamingo": [17160]})
    row = _row_needs_walrus_any()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    fi.handle_focus_cmd(home, "hi bobiverse")

    st_rq, job_rq = gitclaim.offer_focus_top(home, "redqueen-10704", "#redqueen")
    assert st_rq == "empty"
    assert job_rq is None

    st_fl, job_fl = gitclaim.offer_focus_top(home, "flamingo-17160", "#flamingo")
    assert st_fl == "empty"
    assert job_fl is None

    st_w, job_w = gitclaim.offer_focus_top(home, "walrus-1", "#walrus")
    assert st_w == "ok"
    assert job_w is not None
    assert str(job_w.get("id") or "").lstrip("#") == "9664"
    assert gitclaim.row_require_machine(job_w) == "walrus"


def test_fr9664_unpin_without_label_still_clears_soft_cues():
    """Operator any still clears soft body/title cues (FR #9637 / #4512)."""
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#9999",
        "title": "chair: offer_to_idle",
        "body": "require_machine: walrus\n",
        "labels": ["feature-request"],
        "require_machine": "any",
        "require_machine_operator": True,
        "line": "",
    }
    assert gitclaim.row_require_machine(row) == ""
    gitclaim._stamp_require_machine(row)
    assert row.get("require_machine") == "any"
