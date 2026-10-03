"""FR #618: UAT of PR numbers must inherit MRB author stamps at offer time."""
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


def test_enrich_uat_of_pr_from_done_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928, 35600], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#603",
                "seq": 1,
                "ts": "t",
                "line": "UAT SimonBarnett/bobiverse#603",
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
    assert enriched["mrb_author_seat"] == "marchhare-41928"
    assert enriched["implementer_seat"] == "marchhare-35600"


def test_offer_blocks_mrb_author_on_unstamped_uat_pr(tmp_path, monkeypatch):
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
                    "id": "#603",
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT #603",
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
    st, job = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#603"
    assert job2.get("mrb_author_seat") == "marchhare-41928"


def test_enrich_fix_nits_uat_via_mrb_parent_token(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928, 35600], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#629",
                "seq": 1,
                "ts": "t",
                "line": "test(mrb-619): sibling UAT block",
                "title": "test(mrb-619): sibling UAT block for implementer seat",
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#619",
                "nick": "marchhare-41928",
                "implementer_seat": "marchhare-35600",
                "refs": ["#265"],
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched["mrb_author_seat"] == "marchhare-41928"
    assert enriched.get("mrb_fix_author_seat") == "marchhare-41928"


def test_row_author_seats_includes_mrb_fix_author(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928], "ionos": [2]})
    seats = gitclaim.row_author_seats(
        {"task": "UAT", "mrb_fix_author_seat": "marchhare-41928", "author_seat": "ionos-2"}
    )
    assert "marchhare-41928" in seats
    assert "ionos-2" in seats