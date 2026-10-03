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
                    "id": "#0",
                    "repo_uat": True,
                    "refs": ["#603"],
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT owner/repo#0",
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
    assert st2 == "ok" and job2["id"] == "#0"
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

def test_offer_top_blocks_mrb_author_on_unstamped_uat_pr(tmp_path, monkeypatch):
    """FR #618 letter: offer_top (non-focus) must enrich + author-block too."""
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
                    "refs": ["#603"],
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT owner/repo#0",
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
    st, job = gitclaim.offer_top(home, "marchhare-41928", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#0"
    assert job2.get("mrb_author_seat") == "marchhare-41928"


def test_enrich_via_refs_when_uat_is_closes_issue(tmp_path, monkeypatch):
    """UAT #<issue> must match done MRB whose refs include that issue."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [41928], "ionos": [1]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "UAT",
                "id": "#595",
                "seq": 1,
                "ts": "t",
                "line": "UAT #595",
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
                "refs": ["#595"],
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched["mrb_author_seat"] == "marchhare-41928"
    assert enriched["implementer_seat"] == "marchhare-35600"


def test_enrich_first_related_mrb_wins(tmp_path, monkeypatch):
    """When two related MRBs disagree, keep the first stamp (accepted then done order)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest(tmp_path, {"marchhare": [1], "ionos": [2], "flamingo": [3]})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "o/r",
                "task": "UAT",
                "id": "#10",
                "seq": 1,
                "ts": "t",
                "line": "UAT #10",
            }
        ],
        "accepted": [
            {
                "repo": "o/r",
                "task": "MRB",
                "id": "#10",
                "nick": "marchhare-1",
                "implementer_seat": "ionos-2",
                "refs": ["#9"],
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
        "done": [
            {
                "repo": "o/r",
                "task": "MRB",
                "id": "#10",
                "nick": "flamingo-3",
                "implementer_seat": "flamingo-3",
                "refs": ["#9"],
                "seq": 2,
                "ts": "t2",
                "line": "x",
            }
        ],
    }
    enriched = gitclaim.enrich_uat_author_fields(doc, doc["unaccepted"][0])
    assert enriched["mrb_author_seat"] == "marchhare-1"
    assert enriched["implementer_seat"] == "ionos-2"


def test_offer_persists_stamps_so_reoffer_blocks_without_done(tmp_path, monkeypatch):
    """After a third-party offer, stamps stay on the row (GIVEUP / drained-MRB safety)."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    _digest(home, {"marchhare": [41928], "flamingo": [9], "ionos": [1]})
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
                    "refs": ["#603"],
                    "seq": 1,
                    "ts": "t",
                    "line": "UAT owner/repo#0",
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
                    "refs": ["#595"],
                    "seq": 1,
                    "ts": "t",
                    "line": "x",
                }
            ],
        },
    )
    st, job = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st == "ok" and job.get("mrb_author_seat") == "marchhare-41928"
    # Simulate GIVEUP: clear offer stamp, drain done history, keep enriched fields.
    q = gitclaim._load_queue_unlocked(home)
    row = q["unaccepted"][0]
    for k in ("offered_to", "offered_ts", "offered_channel"):
        row.pop(k, None)
    q["done"] = []
    gitclaim._write_queue(gitclaim.queue_path(home), q)
    st2, job2 = gitclaim.offer_focus_top(home, "marchhare-41928", "#marchhare")
    assert st2 == "empty", "persisted mrb_author_seat must still block after done drained"
