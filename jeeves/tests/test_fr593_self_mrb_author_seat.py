"""FR #593: PR-opened MRB must stamp author_seat from FR implementer (block self-MRB)."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines


def test_pr_opened_stamps_author_seat_from_accepted_fr(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#238",
                "seq": 1,
                "nick": "marchhare-35600",
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "pull_request": {
                "number": 273,
                "title": "fix(fr-238)",
                "body": "Closes SimonBarnett/bobiverse#238",
                "html_url": "https://github.com/SimonBarnett/bobiverse/pull/273",
            },
        },
    )
    assert claim is not None and claim.id == "#273"
    assert "#238" in claim.refs
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0]["id"] == "#273"
    assert mrbs[0].get("author_seat") == "marchhare-35600"
    assert mrbs[0].get("implementer_seat") == "marchhare-35600"
    assert mrbs[0].get("url", "").endswith("/pull/273")
    # FR row removed
    assert not any(
        r.get("task") == "FR" and r.get("id") == "#238"
        for r in gitclaim.load_unaccepted(home)
    )


def test_pr_opened_mrb_not_offered_to_implementer_when_other_machine_live(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {"35600": {"state": "idle"}}
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(home, digest)

    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#238",
                "seq": 1,
                "nick": "marchhare-35600",
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "opened",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "pull_request": {
                "number": 273,
                "title": "fix",
                "body": "Closes #238",
                "html_url": "u",
            },
        },
    )
    assert gitclaim.apply_queue_event(home, claim) in ("added", "updated", "duplicate")
    st, job = gitclaim.offer_focus_top(home, "marchhare-35600", "#marchhare")
    assert st == "empty"  # self-MRB blocked
    st2, job2 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#273"


def test_fr_implementer_seat_from_done_bucket(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {
                "repo": "o/r",
                "task": "FR",
                "id": "#1",
                "nick": "marchhare-1",
                "done_by": "marchhare-1",
            }
        ],
    }
    assert gitclaim.fr_implementer_seat_from_doc(doc, "o/r", ["#1"]) == "marchhare-1"
