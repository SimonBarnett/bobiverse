"""FR #5095: DONE matches repo+id+task only; duplicate DONE FIX must not close requeued MRB.

Symptom (a-search #5239): first DONE FIX marked FIX done and requeued MRB (FR #4929);
a second (drain-retry) DONE FIX matched the unaccepted MRB by repo+id alone and
marked it done, so the PR never got an MRB offer.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/a-search"
PR = "#5239"
FIX_SEAT = "marchhare-8328"
OTHER = "flamingo-10001"
URL = f"https://github.com/{REPO}/pull/5239"


def _digest(home: Path) -> None:
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": FIX_SEAT, "state": "idle"},
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": OTHER, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)


def _queue_accepted_fix(home: Path) -> None:
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "nick": FIX_SEAT,
                "url": URL,
                "accepted_ts": "t0",
                "title": "fix tip",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)


def test_second_done_fix_leaves_requeued_mrb_unaccepted(tmp_path, monkeypatch):
    """FIX done + MRB requeued; second DONE FIX is no-op; MRB stays unaccepted."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    _digest(home)
    _queue_accepted_fix(home)

    st1, job1 = shop_listen.complete_job_by_ref(
        home,
        nick=FIX_SEAT,
        repo=REPO,
        task="FIX",
        ident=PR,
        result="PASS",
        url=URL,
    )
    assert st1 == "ok"
    assert job1 is not None
    assert str(job1.get("task") or "").upper() == "FIX"

    q1 = gitclaim.load_queue(home)
    mrb1 = [
        r
        for r in (q1.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
    ]
    assert len(mrb1) == 1, "DONE FIX must requeue MRB (FR #4929)"

    st2, job2 = shop_listen.complete_job_by_ref(
        home,
        nick=FIX_SEAT,
        repo=REPO,
        task="FIX",
        ident=PR,
        result="PASS",
        url=URL,
    )
    assert st2 == "duplicate", f"second DONE FIX must be no-op, got {st2!r}"
    assert job2 is None or str(job2.get("task") or "").upper() == "FIX"

    q2 = gitclaim.load_queue(home)
    mrb2 = [
        r
        for r in (q2.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
    ]
    assert len(mrb2) == 1, "requeued MRB must stay unaccepted after duplicate DONE FIX"
    assert not any(
        str(r.get("task") or "").upper() == "MRB" and str(r.get("id") or "") == PR
        for r in (q2.get("done") or [])
        if isinstance(r, dict)
    ), "MRB must not be marked done by a DONE FIX line"

    # Non-author seat can still be offered the MRB.
    st_o, job_o = gitclaim.offer_focus_top(home, OTHER, "#flamingo")
    assert st_o == "ok"
    assert job_o is not None
    assert str(job_o.get("task") or "").upper() == "MRB"
    assert job_o.get("id") == PR


def test_done_matches_task_not_sibling_row(tmp_path, monkeypatch):
    """DONE MRB must not consume an accepted FIX for the same repo#id."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "flamingo"})
    _digest(home)
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "nick": FIX_SEAT,
                "url": URL,
                "accepted_ts": "t0",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)

    st, job = shop_listen.complete_job_by_ref(
        home,
        nick=OTHER,
        repo=REPO,
        task="MRB",
        ident=PR,
        result="PASS",
        url=URL,
    )
    assert st == "missing"
    assert job is None
    q = gitclaim.load_queue(home)
    assert len(q.get("accepted") or []) == 1
    assert str((q["accepted"][0]).get("task") or "").upper() == "FIX"