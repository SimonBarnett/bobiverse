# -*- coding: utf-8 -*-
"""FR #10200: live webhook / intake 502 ops titles on bobiverse pin the chair host.

Chair-host outages (intake / BobCallback / ARR 502) must never be offered to a
shop seat such as redqueen. Title-only cue: body prose still never pins bobiverse
(FR #9637 / #4512).
"""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines

TITLE = "chair offered ionos-pinned live webhook 502 ops #10107 to redqueen"
BODY = (
    "what: Jeeves assigned FR SimonBarnett/bobiverse#10107 to redqueen-3332 while "
    "infer_require_machine(title+body)=ionos (BobCallback/IIS 502 on walrus). "
    "evidence: monitor filing title live /bob/v1/report|digest|models|intake all 502; "
    "body Fix step 1 On walrus.\n"
)


def test_fr10200_webhook_502_title_pins_chair_host(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "walrus")
    mid = gitclaim.infer_require_machine(
        title=TITLE,
        body=BODY,
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#10107",
    )
    assert mid == "walrus"


def test_fr10200_intake_502_title_variants_pin(monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "walrus")
    for title in (
        "live intake 502 ops: report webhook down",
        "BobCallback 502 on live webhook",
        "ARR webhook 502 after restart",
    ):
        assert (
            gitclaim.infer_require_machine(
                title=title,
                body="",
                labels=["feature-request"],
                repo="SimonBarnett/bobiverse",
                ident="#10107",
            )
            == "walrus"
        ), title


def test_fr10200_body_only_webhook_502_does_not_pin(monkeypatch):
    """FR #9637 preserved: body prose alone must not pin bobiverse."""
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "walrus")
    mid = gitclaim.infer_require_machine(
        title="docs: webhook retry notes",
        body="Historic note: live webhook returned 502 in March; see runbook.\n",
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#10108",
    )
    assert mid == ""


def test_fr10200_offer_skips_redqueen_for_chair_host_webhook_title(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "walrus")
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"walrus", "redqueen"})
    doc = bobreport.empty_digest()
    for mid, pid in (("walrus", 1), ("redqueen", 3332)):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-11-28T02:00:00Z",
            }
        ]
    bobreport.save_digest(home, doc)
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#10107",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#10107",
        "title": TITLE,
        "body": BODY,
        "labels": ["feature-request", "via-intake"],
        "state": "open",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    fi.handle_focus_cmd(home, "hi bobiverse")

    st_rq, job_rq = gitclaim.offer_focus_top(home, "redqueen-3332", "#redqueen")
    assert st_rq == "empty"
    assert job_rq is None

    st_w, job_w = gitclaim.offer_focus_top(home, "walrus-1", "#walrus")
    assert st_w == "ok"
    assert str(job_w.get("id") or "").lstrip("#") == "10107"
