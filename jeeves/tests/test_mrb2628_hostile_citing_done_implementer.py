"""MRB #2628 hostile gates for FR #2623 citing-DONE implementer keep."""
from __future__ import annotations

from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
PULL = "https://github.com/SimonBarnett/bobiverse/pull/2999"
SEAT_A = "marchhare-9524"
SEAT_B = "marchhare-39912"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "9524": {"state": "idle", "nick": SEAT_A},
        "39912": {"state": "idle", "nick": SEAT_B},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept_fr(home, nick: str, issue: str = "#2990") -> None:
    doc = gitclaim._load_queue_unlocked(home)
    doc["accepted"] = [
        r
        for r in (doc.get("accepted") or [])
        if not (
            str(r.get("repo")) == REPO
            and str(r.get("task") or "").upper() == "FR"
            and str(r.get("id")) == issue
        )
    ]
    doc["unaccepted"] = [
        r
        for r in (doc.get("unaccepted") or [])
        if not (
            str(r.get("repo")) == REPO
            and str(r.get("task") or "").upper() == "FR"
            and str(r.get("id")) == issue
        )
    ]
    doc.setdefault("accepted", []).append(
        {
            "repo": REPO,
            "task": "FR",
            "id": issue,
            "seq": 1,
            "nick": nick,
            "ts": "t",
            "line": "x",
            "channel": "#marchhare",
            "accepted_ts": "t",
        }
    )
    gitclaim._write_queue(gitclaim.queue_path(home), doc)


def test_mrb2628_citing_done_ledger_frw_does_not_block_mrb(tmp_path, monkeypatch):
    """t860u FRW on the pull key must not ledger-block the citing seat from MRB."""
    home = _home(tmp_path, monkeypatch)
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": [], "accepted": [], "done": []}
    )
    _accept_fr(home, SEAT_A)
    st, job = shop_listen.complete_job_by_ref(
        home, nick=SEAT_A, repo=REPO, task="FR", ident="#2990", result="", url=PULL
    )
    assert st == "ok"
    gitclaim.ledger_note_event(
        home, SEAT_A, "DONE", "FR", REPO, "#2990", job or {"url": PULL}, url=PULL
    )
    _accept_fr(home, SEAT_B)
    st, job = shop_listen.complete_job_by_ref(
        home, nick=SEAT_B, repo=REPO, task="FR", ident="#2990", result="", url=PULL
    )
    assert st == "ok"
    gitclaim.ledger_note_event(
        home, SEAT_B, "DONE", "FR", REPO, "#2990", job or {"url": PULL}, url=PULL
    )
    led = gitclaim.ledger_load(home)
    touch_pr = (led.get("touch") or {}).get("simonbarnett/bobiverse#2999") or {}
    assert "FRW" in (touch_pr.get(SEAT_B) or [])
    assert "FR" not in (touch_pr.get(SEAT_B) or [])
    mrb = {
        "repo": REPO,
        "task": "MRB",
        "id": "#2999",
        "url": PULL,
        "author_seat": SEAT_A,
        "implementer_seat": SEAT_A,
        "refs": ["#2990"],
        "supersedes": f"{REPO}#2990",
    }
    assert gitclaim.ledger_blocks(led, mrb, SEAT_B, None) == ""
    st_b, job_b = gitclaim.offer_focus_top(home, SEAT_B, "#marchhare")
    assert st_b == "ok"
    assert (job_b.get("task"), job_b.get("id")) == ("MRB", "#2999")


def test_mrb2628_resolver_prefers_mrb_stamp_over_earlier_done(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    doc = {
        "v": 1,
        "unaccepted": [
            {
                "repo": REPO,
                "task": "MRB",
                "id": "#2999",
                "implementer_seat": SEAT_A,
                "author_seat": SEAT_A,
                "url": PULL,
            }
        ],
        "accepted": [],
        "done": [
            {
                "repo": REPO,
                "task": "FR",
                "id": "#2990",
                "nick": "flamingo-1",
                "url": PULL,
            }
        ],
    }
    seat = gitclaim.resolve_done_fr_implementer_seat(
        doc,
        pr_repo=REPO,
        pr_id="#2999",
        issue_repo=REPO,
        issue_id="#2990",
        done_nick=SEAT_B,
    )
    assert seat == SEAT_A


def test_mrb2628_source_keeps_implementer_keys():
    src = Path(gitclaim.__file__).read_text(encoding="utf-8")
    assert "_IMPLEMENTER_KEEP_KEYS" in src
    assert "resolve_done_fr_implementer_seat" in src
    assert "FR #2623" in src
    shop = Path(shop_listen.__file__).read_text(encoding="utf-8")
    assert "resolve_done_fr_implementer_seat" in shop
