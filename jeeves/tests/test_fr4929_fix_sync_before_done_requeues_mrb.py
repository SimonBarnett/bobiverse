"""FR #4929: FIX push synchronize before DONE FIX must not lose the re-MRB.

When synchronize lands while FIX is still accepted, stale MRB done / mrb_done
must be cleared so the new head is offerable. When DONE FIX lands (even if
synchronize was skipped or purged), MRB must be requeued at that PR.
"""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen


REPO = "SimonBarnett/a-search"
PR = "#4705"
FIX_SEAT = "flamingo-73012"
OTHER = "marchhare-18124"
URL = f"https://github.com/{REPO}/pull/4705"
SHA = "380b0a943c658942c6edd51a110de268cbd927ae"


def _digest(home: Path) -> None:
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": FIX_SEAT, "state": "idle"},
        {"nick": OTHER, "state": "idle"},
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": OTHER, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)


def _queue_with_prior_mrb_pass_and_accepted_fix(home: Path) -> None:
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
        "done": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": PR,
                "result": "PASS",
                "done_by": OTHER,
                "url": URL,
                "done_ts": "t-1",
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    gitclaim.stamp_mrb_done(home, REPO, PR)


def test_synchronize_while_fix_accepted_clears_done_and_queues_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    _digest(home)
    _queue_with_prior_mrb_pass_and_accepted_fix(home)
    assert gitclaim.mrb_ledger_done_hold(home, REPO, PR)

    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id=PR,
        event="pull_request",
        action="synchronize",
        line=URL,
        title="feat tip",
        body="Closes SimonBarnett/a-search#4701",
        refs=("#4701",),
    )
    st = gitclaim.apply_queue_event(home, claim)
    assert st in ("added", "updated", "duplicate")

    q = gitclaim.load_queue(home)
    assert not any(
        str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
        for r in (q.get("done") or [])
        if isinstance(r, dict)
    ), "prior MRB PASS must leave done[] so purge cannot drop the requeue"
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, PR)
    mrb = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
    ]
    assert len(mrb) == 1
    assert mrb[0].get("action") == "synchronize"


def test_done_fix_requeues_mrb_when_synchronize_lost(tmp_path, monkeypatch):
    """DONE FIX alone must requeue MRB even if synchronize never left a row."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo", "marchhare"})
    _digest(home)
    _queue_with_prior_mrb_pass_and_accepted_fix(home)

    st, job = shop_listen.complete_job_by_ref(
        home,
        nick=FIX_SEAT,
        repo=REPO,
        task="FIX",
        ident=PR,
        result="PASS",
        url=URL,
    )
    assert st == "ok"
    assert job is not None

    q = gitclaim.load_queue(home)
    assert not gitclaim.mrb_ledger_done_hold(home, REPO, PR)
    mrb = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
        and str(r.get("task") or "").upper() == "MRB"
        and str(r.get("id") or "") == PR
    ]
    assert len(mrb) == 1, "DONE FIX must enqueue MRB for the new head"
    # FIX seat stamped so offer skips self-MRB (FR #4604).
    seats = gitclaim.row_author_seats(gitclaim.enrich_mrb_author_fields(q, mrb[0]))
    assert FIX_SEAT in seats

    st_fix, job_fix = gitclaim.offer_focus_top(home, FIX_SEAT, "#flamingo")
    assert st_fix == "empty" or job_fix is None or str((job_fix or {}).get("id") or "") != PR

    st_o, job_o = gitclaim.offer_focus_top(home, OTHER, "#flamingo")
    assert st_o == "ok"
    assert job_o is not None
    assert job_o.get("id") == PR
