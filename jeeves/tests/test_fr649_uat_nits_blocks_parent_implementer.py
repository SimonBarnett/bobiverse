"""FR #649: UAT of a nits PR must not go to the parent product implementer.

Gap: Jeeves assigned UAT #631 (test-only PASS-nits on #623) to marchhare-41928,
who authored parent PR #623 (FR #269). Prefer UAT of the parent product PR on a
different machine; never offer nits-only UAT to the parent implementer.
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


def test_enrich_nits_uat_stamps_parent_implementer(tmp_path, monkeypatch):
    """UAT #631 titled test(mrb-623) inherits implementer_seat from MRB #623."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928, 35600], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#631",
                "seq": 1,
                "ts": "t",
                "line": "UAT SimonBarnett/bobiverse#631",
                "title": "test(mrb-623): /XO third_party guard + post-install ComposeOnly assert",
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


def test_offer_blocks_parent_implementer_on_nits_uat(tmp_path, monkeypatch):
    """FR #649 acceptance: parent #623 implementer must not get UAT of nits #631."""
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
                    "id": "#0",
                    "repo_uat": True,
                    "refs": ["#631"],
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT owner/repo#0",
                    "title": "UAT owner/repo#0: test mrb-623 nits",
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
    assert st2 == "ok" and job2["id"] == "#0"
    assert job2.get("implementer_seat") == "marchhare-41928"
