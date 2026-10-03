"""FR #665: UAT of an mrb-*-fix PR must not go to the fix/MRB author.

Gap: Jeeves assigned UAT #613 (fix(mrb-603): ...) to marchhare-41928, committer of
that fix PR and MRB reviewer of #603. Self-UAT forbidden (FR #265 / #618).
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


def test_enrich_fix_uat_stamps_mrb_fix_author(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#613",
                "seq": 1,
                "ts": "t",
                "line": "UAT SimonBarnett/bobiverse#613",
                "title": "fix(mrb-603): line-text verdict skip + pull URL repo match",
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#603",
                "seq": 1,
                "nick": "marchhare-41928",
                "implementer_seat": "marchhare-35600",
                "author_seat": "marchhare-35600",
                "refs": ["#595"],
                "ts": "t",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched.get("mrb_author_seat") == "marchhare-41928"
    assert enriched.get("mrb_fix_author_seat") == "marchhare-41928"
    assert enriched.get("implementer_seat") == "marchhare-35600"
    seats = gitclaim.row_author_seats(enriched)
    assert "marchhare-41928" in seats
    assert "marchhare-35600" in seats


def test_offer_blocks_fix_author_on_uat_of_own_fix_pr(tmp_path, monkeypatch):
    """FR #665 acceptance: fix/MRB author must not get UAT of #613."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [41928], "ionos": [1], "flamingo": [9]})
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "UAT",
                    "id": "#613",
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT SimonBarnett/bobiverse#613",
                    "title": "fix(mrb-603): line-text verdict skip + pull URL repo match",
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#603",
                    "nick": "marchhare-41928",
                    "implementer_seat": "marchhare-35600",
                    "author_seat": "marchhare-35600",
                    "refs": ["#595"],
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )
    st, _ = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#613"
    assert job2.get("mrb_fix_author_seat") == "marchhare-41928"
