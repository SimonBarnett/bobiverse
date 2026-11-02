"""FR #5900: idle non-author same-machine seat must be offerable after Copilot give-up.

unaccepted_starved must not fire when the only idle seats are authors (that is
no_eligible_reviewer / author-only, not an offer gap). A live sibling who is not
the implementer must get the MRB on !bored once Copilot cooldown expires.
"""
from __future__ import annotations

import time

import bobreport
import focus_ignore
import gitclaim
import registered_machines
import stuck_job_sweep as sweep

REPO = "SimonBarnett/bobiverse"
AUTHOR = "flamingo-37172"
SIBLING = "flamingo-72904"
NOW = 1_800_000_000.0


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": AUTHOR, "state": "idle"},
        {"nick": SIBLING, "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    focus_ignore.handle_focus_cmd(tmp_path, f"high {REPO}")
    return tmp_path


def _mrb_row(*, authors=None, giveup="copilot", age_s=4000):
    authors = list(authors or [AUTHOR])
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - float(age_s)))
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#5866",
        "seq": 1,
        "url": f"https://github.com/{REPO}/pull/5866",
        "author_seat": authors[0],
        "implementer_seat": authors[0],
        "giveup_seats": giveup,
        "giveup_ts": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 3600)
        ),
        "ts": ts,
        "event": "pull_request",
        "line": "MRB",
        "title": "fr-5865 CodeRabbit-first",
    }
    if len(authors) > 1:
        row["author_seats"] = ",".join(authors)
    return row


def test_fr5900_sibling_offered_after_copilot_giveup(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = _mrb_row()
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    live = gitclaim.live_seat_nicks(home)
    assert AUTHOR in live and SIBLING in live
    assert gitclaim.review_blocked_for_author(row, AUTHOR, live) is True
    assert gitclaim.review_blocked_for_author(row, SIBLING, live) is False
    stats = gitclaim.summarize_empty_offer(home, SIBLING)
    assert stats["self_mrb"] == 0
    assert stats["offerable"] >= 1
    status, job = gitclaim.offer_focus_top(
        home,
        SIBLING,
        "#flamingo",
        now=NOW,
        pr_exists=lambda *_a, **_k: True,
    )
    assert status == "ok"
    assert job["id"] == "#5866"
    assert job["offered_to"] == SIBLING


def test_fr5900_unaccepted_starved_requires_eligible_idle(tmp_path, monkeypatch):
    """Author-only idle must not look like unaccepted_starved (FR #5900)."""
    home = _home(tmp_path, monkeypatch)
    row = _mrb_row(age_s=max(sweep.UNACCEPTED_STARVE_S, 4000) + 10)
    # Only the author is idle; sibling is live but busy (not in idle set).
    # Busy sibling still counts as an eligible reviewer, so this is not
    # no_eligible_reviewer --- and author-only idle must not be unaccepted_starved.
    live = {AUTHOR, SIBLING}
    idle_author_only = {AUTHOR}
    classified = sweep.classify_queue_row(
        row,
        bucket="unaccepted",
        now=NOW,
        live=live,
        idle=idle_author_only,
        home=home,
        ledger={},
    )
    assert classified["stuck_reason"] != "unaccepted_starved"
    assert classified.get("rule") != "no_eligible_reviewer"

    # Author is the only live human => true no_eligible_reviewer.
    classified_solo = sweep.classify_queue_row(
        row,
        bucket="unaccepted",
        now=NOW,
        live={AUTHOR},
        idle={AUTHOR},
        home=home,
        ledger={},
    )
    assert classified_solo["stuck"] is True
    assert classified_solo["stuck_reason"] == "no_eligible_reviewer"

    # Sibling idle + eligible => true starve (offer gap), not no_eligible.
    classified2 = sweep.classify_queue_row(
        row,
        bucket="unaccepted",
        now=NOW,
        live=live,
        idle={AUTHOR, SIBLING},
        home=home,
        ledger={},
    )
    assert classified2["stuck"] is True
    assert classified2["stuck_reason"] == "unaccepted_starved"
    assert classified2.get("rule") != "no_eligible_reviewer"


def test_fr5900_idle_seats_monitor_uses_mrb_enrichment(tmp_path, monkeypatch):
    """Monitor must use enrich_review_author_fields (not UAT enrich) for MRB rows."""
    import sys
    from pathlib import Path

    mon_dir = Path(__file__).resolve().parents[1] / "tools" / "monitor"
    sys.path.insert(0, str(mon_dir))
    import idle_seats as mon  # noqa: E402

    home = _home(tmp_path, monkeypatch)
    row = _mrb_row()
    doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
    gitclaim._write_queue(gitclaim.queue_path(home), doc)
    live = gitclaim.live_seat_nicks(home)
    ledger = gitclaim.ledger_load(home)
    assert mon._row_offerable_to_nick(
        gitclaim, doc, ledger, live, row, SIBLING, NOW
    )
    assert not mon._row_offerable_to_nick(
        gitclaim, doc, ledger, live, row, AUTHOR, NOW
    )


def test_fr5900_starve_uses_enriched_fix_authors(tmp_path, monkeypatch):
    """Hostile: starve eligibility must enrich FIX seats onto the MRB row."""
    home = _home(tmp_path, monkeypatch)
    # MRB has no author stamp; FIX DONE by AUTHOR for the same pull.
    mrb = {
        "repo": REPO,
        "task": "MRB",
        "id": "#5866",
        "seq": 1,
        "url": f"https://github.com/{REPO}/pull/5866",
        "giveup_seats": "copilot",
        "giveup_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 3600)),
        "ts": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(NOW - float(max(sweep.UNACCEPTED_STARVE_S, 4000) + 10)),
        ),
        "event": "pull_request",
        "line": "MRB",
        "title": "fr-5865",
    }
    fix_done = {
        "repo": REPO,
        "task": "FIX",
        "id": "#5866",
        "url": f"https://github.com/{REPO}/pull/5866",
        "done_by": AUTHOR,
        "nick": AUTHOR,
        "result": "DONE",
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [mrb], "accepted": [], "done": [fix_done]},
    )
    live = {AUTHOR, SIBLING}
    # Author-only idle: after enrich, AUTHOR is blocked => not unaccepted_starved.
    classified = sweep.classify_queue_row(
        mrb,
        bucket="unaccepted",
        now=NOW,
        live=live,
        idle={AUTHOR},
        home=home,
        ledger={},
    )
    assert classified.get("stuck_reason") != "unaccepted_starved"
    # Sibling idle => true starve (offer gap).
    classified2 = sweep.classify_queue_row(
        mrb,
        bucket="unaccepted",
        now=NOW,
        live=live,
        idle={AUTHOR, SIBLING},
        home=home,
        ledger={},
    )
    assert classified2.get("stuck") is True
    assert classified2.get("stuck_reason") == "unaccepted_starved"
