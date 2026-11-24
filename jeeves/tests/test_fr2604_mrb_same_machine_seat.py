"""FR #2604: MRB self-exclusion is per seat; DONE FR stamps pull URL; resync logs skips."""
from __future__ import annotations

import gitclaim
import bobreport
import registered_machines
import shop_listen


def test_fr2604_done_fr_queues_mrb_with_pull_url(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#2601",
                "seq": 1,
                "nick": "marchhare-39912",
                "ts": "t",
                "line": "x",
                "channel": "#marchhare",
                "accepted_ts": "t",
            }
        ],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = shop_listen.complete_job_by_ref(
        tmp_path,
        nick="marchhare-39912",
        repo="SimonBarnett/bobiverse",
        task="FR",
        ident="#2601",
        result="PASS",
        url="https://github.com/SimonBarnett/bobiverse/pull/2602",
    )
    assert st == "ok"
    mrbs = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    assert len(mrbs) == 1
    assert mrbs[0]["id"] == "#2602"
    assert "/pull/2602" in str(mrbs[0].get("url") or "")
    assert mrbs[0].get("author_seat") == "marchhare-39912"
    assert gitclaim.mrb_row_offerable(mrbs[0]) is True


def test_fr2604_sibling_same_machine_allowed_exact_seat(
    tmp_path, monkeypatch
):
    """FR #9574 / #2604: exact author blocked; same-machine sibling eligible."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-39912", "state": "idle"},
        {"nick": "marchhare-9524", "state": "idle"},
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)

    row = {
        "repo": "SimonBarnett/bobiverse",
        "task": "MRB",
        "id": "#2602",
        "url": "https://github.com/SimonBarnett/bobiverse/pull/2602",
        "author_seat": "marchhare-39912",
        "implementer_seat": "marchhare-39912",
        "event": "pull_request",
    }
    live = gitclaim.live_seat_nicks(tmp_path)
    assert "flamingo-9" in live
    assert gitclaim.review_blocked_for_author(row, "marchhare-39912", live) is True
    assert gitclaim.review_blocked_for_author(row, "marchhare-9524", live) is False
    assert gitclaim.review_blocked_for_author(row, "flamingo-9", live) is False


def test_fr2604_offer_focus_top_sibling_and_other_machine(tmp_path, monkeypatch):
    """FR #9574: sibling and other-machine seats both offerable; exact author empty."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": "marchhare-39912", "state": "idle"},
        {"nick": "marchhare-9524", "state": "idle"},
    ]
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": "flamingo-9", "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)

    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "MRB",
                "id": "#2602",
                "seq": 1,
                "url": "https://github.com/SimonBarnett/bobiverse/pull/2602",
                "author_seat": "marchhare-39912",
                "implementer_seat": "marchhare-39912",
                "event": "pull_request",
                "action": "opened",
                "line": "MRB",
                "ts": "t",
            }
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st, job = gitclaim.offer_focus_top(tmp_path, "marchhare-39912", "#marchhare")
    assert st == "empty"
    st2, job2 = gitclaim.offer_focus_top(tmp_path, "marchhare-9524", "#marchhare")
    assert st2 == "ok" and job2["id"] == "#2602"
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    st3, job3 = gitclaim.offer_focus_top(tmp_path, "flamingo-9", "#flamingo")
    assert st3 == "ok" and job3["id"] == "#2602"


def test_fr2604_resync_skips_draft_and_logs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})

    def fetch(url: str):
        if "/pulls?" in url and "state=open" in url:
            return [
                {
                    "number": 2602,
                    "title": "fix(tray): heal",
                    "body": "Closes #2601",
                    "draft": False,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2602",
                },
                {
                    "number": 2598,
                    "title": "harvest: receipt",
                    "body": "Session summary",
                    "draft": True,
                    "html_url": "https://github.com/SimonBarnett/bobiverse/pull/2598",
                },
            ]
        if "/issues?" in url:
            return []
        return []

    stats = gitclaim.resync_from_github(
        tmp_path, ["SimonBarnett/bobiverse"], fetch_json=fetch
    )
    mrbs = [r for r in gitclaim.load_unaccepted(tmp_path) if r.get("task") == "MRB"]
    assert [r["id"] for r in mrbs] == ["#2602"]
    assert "/pull/2602" in str(mrbs[0].get("url") or "")
    # Skip reason for draft must be recorded on the stats / log surface.
    assert int(stats.get("skipped_draft") or 0) >= 1 or "draft" in str(stats).lower()
