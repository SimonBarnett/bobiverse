"""FR #265: UAT must block both FR implementer and MRB author seats."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines
import shop_listen


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{seq:02d}Z",
        "line": "x",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": [], "done": []}
    )


def test_row_author_seats_collects_implementer_and_mrb(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "ionos"})
    seats = gitclaim.row_author_seats(
        {
            "task": "UAT",
            "author_seat": "marchhare-1",
            "implementer_seat": "marchhare-1",
            "mrb_author_seat": "ionos-2",
        }
    )
    assert "marchhare-1" in seats
    assert "ionos-2" in seats


def test_uat_blocks_implementer_even_when_mrb_author_differs(tmp_path, monkeypatch):
    """If MRB reviewer != FR implementer, both must be blocked while another machine is live."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos", "flamingo"})
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {"1": {"state": "idle"}}
    doc["machines"]["ionos"] = bobreport._empty_machine("ionos")
    doc["machines"]["ionos"]["workers"] = {"2": {"state": "idle"}}
    doc["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    doc["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(home, doc)

    _queue(
        home,
        [
            _row(
                "o/r",
                "UAT",
                10,
                1,
                implementer_seat="marchhare-1",
                mrb_author_seat="ionos-2",
                author_seat="ionos-2",  # legacy primary = MRB only
            ),
            _row("o/r", "FR", 99, 2),
        ],
    )
    # Implementer must not get UAT
    st, job = gitclaim.offer_focus_top(home, "marchhare-1", "#marchhare")
    assert st == "ok" and job["id"] == "#99"
    # MRB author must not get UAT
    _queue(
        home,
        [
            _row(
                "o/r",
                "UAT",
                10,
                1,
                implementer_seat="marchhare-1",
                mrb_author_seat="ionos-2",
                author_seat="ionos-2",
            )
        ],
    )
    st2, job2 = gitclaim.offer_focus_top(home, "ionos-2", "#ionos")
    assert st2 == "empty"
    # Third machine may take it
    st3, job3 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st3 == "ok" and job3["id"] == "#10"


def test_done_mrb_pass_stamps_both_implementer_and_mrb_on_uat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": "o/r",
                "task": "MRB",
                "id": "#12",
                "seq": 1,
                "nick": "ionos-2",
                "refs": ["#10"],
                # FR implementer stamped when DONE FR queued this MRB
                "author_seat": "marchhare-1",
                "implementer_seat": "marchhare-1",
                "ts": "t",
                "line": "x",
                "channel": "#ionos",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    st, _job = shop_listen.complete_job_by_ref(
        home,
        repo="o/r",
        task="MRB",
        ident="#12",
        nick="ionos-2",
        result="PASS",
        url="https://example/pull/12",
    )
    assert st == "ok"
    # t853u: no per-issue UAT row any more (repo-level UAT only); the seat ledger records who did what
    assert [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "UAT"] == []


def test_done_fr_stamps_implementer_on_mrb(tmp_path, monkeypatch):
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
                "id": "#265",
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
    st, _job = shop_listen.complete_job_by_ref(
        home,
        repo="SimonBarnett/bobiverse",
        task="FR",
        ident="#265",
        nick="marchhare-35600",
        result="PASS",
        url="https://github.com/SimonBarnett/bobiverse/pull/999",
    )
    assert st == "ok"
    mrbs = [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0].get("implementer_seat") == "marchhare-35600"
    assert mrbs[0].get("author_seat") == "marchhare-35600"


def test_merged_pr_copies_both_seats_onto_uat(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos"})
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9",
                "seq": 1,
                "ts": "t",
                "line": "x",
            }
        ],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#9",
                "seq": 1,
                "nick": "ionos-2",
                "refs": ["#5"],
                "author_seat": "marchhare-1",
                "implementer_seat": "marchhare-1",
                "ts": "t",
                "line": "x",
                "channel": "#ionos",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    claim = gitclaim.claim_from_payload(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": "SimonBarnett/bobiverse"},
            "pull_request": {
                "number": 9,
                "title": "fix",
                "body": "Closes SimonBarnett/bobiverse#5",
                "merged": True,
                "html_url": "u",
            },
        },
    )
    assert gitclaim.apply_queue_event(home, claim) == "updated"
    assert [r for r in gitclaim.load_unaccepted(home) if r.get("task") == "UAT"] == []   # t853u


def test_uat_blocks_same_machine_sibling_of_implementer(tmp_path, monkeypatch):
    """PASS-nits MRB #619: marchhare-2 must not UAT when implementer is marchhare-1 and another machine is live."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"marchhare", "ionos", "flamingo"})
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    doc["machines"]["marchhare"]["workers"] = {"1": {"state": "idle"}, "2": {"state": "idle"}}
    doc["machines"]["ionos"] = bobreport._empty_machine("ionos")
    doc["machines"]["ionos"]["workers"] = {"2": {"state": "idle"}}
    doc["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    doc["machines"]["flamingo"]["workers"] = {"9": {"state": "idle"}}
    bobreport.save_digest(home, doc)
    _queue(
        home,
        [
            _row(
                "o/r",
                "UAT",
                10,
                1,
                implementer_seat="marchhare-1",
                mrb_author_seat="ionos-2",
                author_seat="ionos-2",
            )
        ],
    )
    st, job = gitclaim.offer_focus_top(home, "marchhare-2", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(home, "flamingo-9", "#flamingo")
    assert st2 == "ok" and job2["id"] == "#10"
