"""FR #4695: issues reopened must clear fr_done so seats can take the FR without !resync."""
from __future__ import annotations

import bobreport
import gitclaim
import registered_machines

REPO = "SimonBarnett/a-search"
IDENT = "#3968"
SEAT = "win-mpre8vi4u6u-5772"
SEAT2 = "win-mpre8vi4u6u-14652"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"win-mpre8vi4u6u", "marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["win-mpre8vi4u6u"] = bobreport._empty_machine("win-mpre8vi4u6u")
    digest["machines"]["win-mpre8vi4u6u"]["workers"] = {
        "5772": {"state": "idle", "nick": SEAT},
        "14652": {"state": "idle", "nick": SEAT2},
    }
    digest["machines"]["win-mpre8vi4u6u"]["worker_list"] = [
        {"nick": SEAT, "state": "idle"},
        {"nick": SEAT2, "state": "idle"},
    ]
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _stamp_fr_done(home, repo=REPO, ident=IDENT):
    key = gitclaim._lkey(repo, ident)

    def _stamp(doc: dict) -> None:
        doc.setdefault("fr_done", {})[key] = gitclaim._utc_now()

    gitclaim._ledger_update(home, _stamp)
    return key


def _done_fr(ident=IDENT):
    return {
        "repo": REPO,
        "task": "FR",
        "id": ident,
        "seq": 1,
        "ts": "2026-10-18T09:00:00Z",
        "line": "DONE FR",
        "url": "https://github.com/SimonBarnett/a-search/pull/3973",
        "result": "PASS",
        "done_ts": "2026-10-18T09:23:25Z",
        "nick": "flamingo-30252",
    }


def _reopen_claim(ident=IDENT):
    return gitclaim.GitClaim(
        repo=REPO,
        task="FR",
        id=ident,
        event="issues",
        action="reopened",
        line="GIT issues reopened",
        title="deploy target still missing",
        body="reopened after merge did not meet FR",
        labels=["feature-request"],
        state="open",
        opened_by="SimonBarnett",
    )


def test_reopen_clears_fresh_fr_done_and_assign_offers(tmp_path, monkeypatch, capsys):
    """fr_done < 24h + issues reopened → stamp gone; !bored offers; !assign accepts."""
    home = _home(tmp_path, monkeypatch)
    key = _stamp_fr_done(home)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [], "done": [_done_fr()]},
    )

    led_before = gitclaim.ledger_load(home)
    assert key in (led_before.get("fr_done") or {})
    why_before = gitclaim.ledger_blocks(
        led_before,
        {"repo": REPO, "task": "FR", "id": IDENT},
        SEAT,
        None,
    )
    assert "already delivered" in why_before

    changed = gitclaim.apply_queue_event(home, _reopen_claim())
    assert changed in ("added", "updated", "duplicate")

    out = capsys.readouterr().out
    assert f"INFO reopen cleared fr_done {REPO}{IDENT}" in out

    led = gitclaim.ledger_load(home)
    assert key not in (led.get("fr_done") or {})
    assert (
        gitclaim.ledger_blocks(
            led, {"repo": REPO, "task": "FR", "id": IDENT}, SEAT, None
        )
        == ""
    )

    doc = gitclaim._load_queue_unlocked(home)
    rows = [
        r
        for r in (doc.get("unaccepted") or [])
        if str(r.get("task") or "").upper() == "FR" and r.get("id") == IDENT
    ]
    assert len(rows) == 1

    st_offer, job = gitclaim.offer_focus_top(home, SEAT, "#win-mpre8vi4u6u")
    assert st_offer == "ok"
    assert job.get("task") == "FR"
    assert job.get("id") == IDENT

    # Fresh sibling seat + clear offer stamp: !assign must also accept (not ledger-held).
    with gitclaim._lock(home):
        doc2 = gitclaim._load_queue_unlocked(home)
        for r in doc2.get("unaccepted") or []:
            if r.get("id") == IDENT and str(r.get("task") or "").upper() == "FR":
                r.pop("offered_to", None)
                r.pop("offered_ts", None)
        gitclaim._write_queue(gitclaim.queue_path(home), doc2)

    st_asg, detail = gitclaim.assign_row(
        home,
        SEAT2,
        REPO,
        "FR",
        "3968",
        issue_open=lambda *_a, **_k: True,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: False,
    )
    assert st_asg == "ok", detail


def test_fr_done_with_open_closes_no_reopen_still_blocks(tmp_path, monkeypatch):
    """#1307 / #2617: fresh fr_done + no reopen keeps ledger hold (PR pending merge)."""
    home = _home(tmp_path, monkeypatch)
    key = _stamp_fr_done(home)
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "FR",
                    "id": IDENT,
                    "seq": 1,
                    "ts": "t",
                    "line": "FR still queued somehow",
                    "title": "deploy target",
                    "labels": ["feature-request"],
                    "state": "open",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    led = gitclaim.ledger_load(home)
    assert key in (led.get("fr_done") or {})
    why = gitclaim.ledger_blocks(
        led, {"repo": REPO, "task": "FR", "id": IDENT}, SEAT, None
    )
    assert why == "FR already delivered (PR pending merge)"

    st_offer, _job = gitclaim.offer_focus_top(home, SEAT, "#win-mpre8vi4u6u")
    assert st_offer != "ok"

    st_asg, detail = gitclaim.assign_row(
        home,
        SEAT,
        REPO,
        "FR",
        "3968",
        issue_open=lambda *_a, **_k: True,
        is_pull=lambda *_a, **_k: False,
        pr_exists=lambda *_a, **_k: True,  # open Closes-PR still present
    )
    assert st_asg == "refused"
    assert "already delivered" in str(detail)


def test_closed_unmerged_pr_ref_requeue_also_clears_fr_done(tmp_path, monkeypatch, capsys):
    """FR #4656 path: closed-unmerged PR that requeues an open issue clears fr_done too."""
    home = _home(tmp_path, monkeypatch)
    key = _stamp_fr_done(home, ident="#3017")
    monkeypatch.setattr(
        gitclaim,
        "github_is_pull_checker",
        lambda **_k: (lambda _repo, _num: False),
    )
    monkeypatch.setattr(
        gitclaim,
        "github_issue_open_checker",
        lambda **_k: (lambda _repo, _num: True),
    )
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [],
            "accepted": [],
            "done": [_done_fr(ident="#3017")],
        },
    )
    claim = gitclaim.GitClaim(
        repo=REPO,
        task="MRB",
        id="#3471",
        event="pull_request",
        action="closed",
        line="GIT pull_request closed",
        title="docs",
        body="Refs SimonBarnett/a-search#3017",
        refs=("#3017",),
        merged=False,
    )
    gitclaim.apply_queue_event(home, claim)
    out = capsys.readouterr().out
    assert f"INFO reopen cleared fr_done {REPO}#3017" in out
    led = gitclaim.ledger_load(home)
    assert key not in (led.get("fr_done") or {})
    assert (
        gitclaim.ledger_blocks(
            led, {"repo": REPO, "task": "FR", "id": "#3017"}, SEAT, None
        )
        == ""
    )
