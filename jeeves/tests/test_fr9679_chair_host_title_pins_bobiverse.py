# -*- coding: utf-8 -*-
"""FR #9679: bobiverse chair-host titles still pin walrus after FR #9637."""
from __future__ import annotations

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines


def test_fr9679_chair_host_title_pins_without_label():
    mid = gitclaim.infer_require_machine(
        title="chair-host: install tip after exact-nick self-MRB code (#9670) — Ergo server from config",
        body=(
            "Depends-on: #9668\n"
            "require_machine: <value of BOB_CHAIR_MACHINE / chair Ergo host config>\n"
            "Legacy label needs-walrus alias for that configured host.\n"
        ),
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#9672",
    )
    assert mid == "walrus"


def test_fr9679_body_require_machine_walrus_alone_still_clears():
    """FR #9637 preserved: monitor paste must not pin."""
    mid = gitclaim.infer_require_machine(
        title="chair: sticky offered + NAK !BORED busy while digest idle",
        body="require_machine: walrus\nRefs: #9628\n",
        labels=["feature-request", "via-intake"],
        repo="SimonBarnett/bobiverse",
        ident="#9633",
    )
    assert mid == ""


def test_fr9679_offer_skips_flamingo_for_chair_host_title(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"walrus", "flamingo"})
    doc = bobreport.empty_digest()
    for mid, pid in (("walrus", 1), ("flamingo", 17068)):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["worker_list"] = [
            {
                "nick": f"{mid}-{pid}",
                "state": "idle",
                "work": "",
                "updated": "2026-11-24T15:00:00Z",
            }
        ]
    bobreport.save_digest(home, doc)
    row = {
        "task": "FR",
        "repo": "SimonBarnett/bobiverse",
        "id": "#9672",
        "seq": 1,
        "ts": "t",
        "line": "FR SimonBarnett/bobiverse#9672",
        "title": "chair-host: install tip after exact-nick self-MRB code (#9670)",
        "body": "Ergo server from config; BOB_CHAIR_MACHINE; needs-walrus alias.\n",
        "labels": ["feature-request", "via-intake"],
        "state": "open",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    fi.handle_focus_cmd(home, "hi bobiverse")
    assert gitclaim.row_require_machine(gitclaim.load_unaccepted(home)[0]) == "walrus"

    st_fl, job_fl = gitclaim.offer_focus_top(home, "flamingo-17068", "#flamingo")
    assert st_fl == "empty"
    assert job_fl is None

    st_w, job_w = gitclaim.offer_focus_top(home, "walrus-1", "#walrus")
    assert st_w == "ok"
    assert job_w is not None
    assert str(job_w.get("id") or "").lstrip("#") == "9672"
