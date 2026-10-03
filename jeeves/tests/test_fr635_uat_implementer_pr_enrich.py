"""FR #635: UAT of an implementer's own PR must not be offered to that seat.

Reproduces the gap: Jeeves assigned UAT bobiverse#623 to marchhare-41928, the
committer of PR #623 (FR #269). DONE MRB often stamps UAT on the Closes issue id,
so the PR-number UAT row arrives unstamped — enrich from related MRB at offer time.
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


def test_enrich_uat_of_implementer_pr_from_done_mrb(tmp_path, monkeypatch):
    """UAT #623 unstamped inherits implementer_seat from done MRB #623."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928, 35600], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#623",
                "seq": 1,
                "ts": "t",
                "line": "UAT SimonBarnett/bobiverse#623",
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#623",
                "seq": 1,
                "nick": "flamingo-9",
                "implementer_seat": "marchhare-41928",
                "author_seat": "marchhare-41928",
                "refs": ["#269"],
                "ts": "t",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched["implementer_seat"] == "marchhare-41928"
    assert "marchhare-41928" in gitclaim.row_author_seats(enriched)


def test_offer_blocks_implementer_on_unstamped_uat_of_own_pr(tmp_path, monkeypatch):
    """FR #635 acceptance: marchhare-41928 must not be offered UAT of own PR #623."""
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
                    "id": "#623",
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT SimonBarnett/bobiverse#623",
                }
            ],
            "accepted": [],
            "done": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#623",
                    "nick": "flamingo-9",
                    "implementer_seat": "marchhare-41928",
                    "author_seat": "marchhare-41928",
                    "refs": ["#269"],
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "ionos-1", "#ionos")
    assert st2 == "ok" and job2["id"] == "#623"
    assert job2.get("implementer_seat") == "marchhare-41928"


def test_enrich_via_closes_issue_ref(tmp_path, monkeypatch):
    """UAT of closed FR #269 still picks up implementer from MRB that refs #269."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#269",
                "seq": 1,
                "ts": "t",
                "line": "UAT #269",
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#623",
                "nick": "flamingo-9",
                "implementer_seat": "marchhare-41928",
                "refs": ["#269"],
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched["implementer_seat"] == "marchhare-41928"
