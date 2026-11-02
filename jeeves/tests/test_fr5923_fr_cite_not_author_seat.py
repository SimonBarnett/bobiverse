"""FR #5923: FR job that only cites a PR must not become MRB author_seats.

fix_ci_seats_from_doc previously treated DONE FR with /pull/N in result as
authorship. That blocked flamingo-21560 on #5914 even though every commit was
by flamingo-60120 (cite-only / informational FR).
"""
from __future__ import annotations

import bobreport
import focus_ignore
import gitclaim
import registered_machines

REPO = "SimonBarnett/bobiverse"
PR = "#5914"
AUTHOR = "flamingo-60120"
CITER = "flamingo-21560"
URL = f"https://github.com/{REPO}/pull/5914"


def _digest(home):
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": AUTHOR, "state": "idle"},
        {"nick": CITER, "state": "idle"},
    ]
    bobreport.save_digest(home, digest)


def test_fr_cite_only_not_in_fix_ci_seats(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    doc = {
        "v": 1,
        "unaccepted": [],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#5905",
                "done_by": CITER,
                "nick": CITER,
                # Cite-only: DONE result is the PR URL (live #5914 class).
                "result": URL,
                "url": URL,
            }
        ],
    }
    assert gitclaim.fix_ci_seats_from_doc(doc, REPO, PR) == []
    mrb = {
        "repo": REPO,
        "task": "MRB",
        "id": PR,
        "url": URL,
        "author_seat": AUTHOR,
        "implementer_seat": AUTHOR,
    }
    enriched = gitclaim.enrich_mrb_author_fields(doc, mrb)
    seats = gitclaim.row_author_seats(enriched)
    assert AUTHOR in seats
    assert CITER not in seats


def test_fix_seat_still_blocked_and_commit_author_stays(tmp_path, monkeypatch):
    """Regression: FIX seat stays blocked; real commit author stays blocked."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    _digest(tmp_path)
    fix_seat = "flamingo-99999"
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": PR,
                "url": URL,
                "author_seat": AUTHOR,
                "implementer_seat": AUTHOR,
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FIX",
                "id": PR,
                "done_by": fix_seat,
                "nick": fix_seat,
                "url": URL,
                "result": "PASS",
            },
            {
                "repo": REPO,
                "task": "FR",
                "id": "#1",
                "done_by": CITER,
                "result": URL,
            },
        ],
    }
    seats = gitclaim.fix_ci_seats_from_doc(doc, REPO, PR)
    assert fix_seat in seats
    assert CITER not in seats
    enriched = gitclaim.enrich_mrb_author_fields(doc, doc["unaccepted"][0])
    authors = gitclaim.row_author_seats(enriched)
    assert AUTHOR in authors
    assert fix_seat in authors
    assert CITER not in authors
    live = {AUTHOR, CITER, fix_seat}
    assert gitclaim.review_blocked_for_author(enriched, AUTHOR, live) is True
    assert gitclaim.review_blocked_for_author(enriched, fix_seat, live) is True
    assert gitclaim.review_blocked_for_author(enriched, CITER, live) is False


def test_offer_focus_top_offers_citer_not_author(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    registered_machines.save_registered(home, {"flamingo"})
    _digest(home)
    focus_ignore.handle_focus_cmd(home, f"high {REPO}")
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": PR,
                "seq": 1,
                "ts": "t",
                "line": "x",
                "url": URL,
                "event": "pull_request",
                "author_seat": AUTHOR,
                "implementer_seat": AUTHOR,
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#5905",
                "done_by": CITER,
                "result": URL,
            }
        ],
    }
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    status, job = gitclaim.offer_focus_top(
        home,
        CITER,
        "#flamingo",
        now=1_900_000_000.0,
        pr_exists=lambda *_a, **_k: True,
    )
    assert status == "ok", status
    assert job and job.get("id") == PR
    assert job.get("offered_to") == CITER
