"""FR #680: UAT of mrb-fix #640 must not go to parent FR #611 implementer.

Gap: Jeeves assigned UAT #640 (fix(mrb-626)) to marchhare-35600, who authored
Fixes PR #626. Enrich must stamp implementer_seat from related MRB #626.
"""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def _digest(home, machines):
    registered_machines.save_registered(home, set(machines))
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {str(w): {"state": "idle"} for w in workers}
    bobreport.save_digest(home, doc)


def test_offer_blocks_parent_implementer_on_mrb_626_fix_uat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [35600, 41928], "ionos": [1], "flamingo": [9]})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "UAT",
                    "id": "#0",
                    "repo_uat": True,
                    "refs": ["#640"],
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT owner/repo#0",
                    "title": "UAT owner/repo#0: mrb-626 patch",
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#626",
                    "nick": "marchhare-41928",
                    "implementer_seat": "marchhare-35600",
                    "author_seat": "marchhare-35600",
                    "refs": ["#611"],
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )
    st, _ = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#0"
    assert job2.get("implementer_seat") == "marchhare-35600"
    assert job2.get("mrb_fix_author_seat") == "marchhare-41928"
