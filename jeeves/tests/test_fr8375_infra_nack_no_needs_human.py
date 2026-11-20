"""FR #8375: infra/soft NACK must not stamp needs_human.

Three infra reasons (hard ceiling, worktree-create-failed, holder_bored) leave
the row offerable to a fresh nick. Two product GIVEUPs still stamp.
"""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT_A = "flamingo-37200"
SEAT_B = "flamingo-48824"
SEAT_C = "flamingo-83750"
FRESH = "marchhare-18680"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["workers"] = {
        "37200": {"state": "idle", "nick": SEAT_A},
        "48824": {"state": "idle", "nick": SEAT_B},
        "83750": {"state": "idle", "nick": SEAT_C},
    }
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["workers"] = {
        "18680": {"state": "idle", "nick": FRESH},
    }
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def _accept(doc, nick, ident="#8375"):
    un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == ident]
    if not un:
        return doc
    job = dict(un[0])
    job["nick"] = nick
    doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != ident]
    doc.setdefault("accepted", []).append(job)
    return doc


def _seed(home, nick):
    row = {
        "repo": REPO,
        "task": "FR",
        "id": "#8375",
        "nick": nick,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/issues/8375",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )


def test_infra_classifier_covers_the_soft_reasons():
    assert gitclaim.is_infra_soft_giveup_reason("hard ceiling 1800000ms")
    assert gitclaim.is_infra_soft_giveup_reason("worktree-create-failed:no-clone")
    assert gitclaim.is_infra_soft_giveup_reason("holder_bored")
    assert gitclaim.is_infra_soft_giveup_reason("offer-timeout")
    assert gitclaim.is_infra_soft_giveup_reason("cannot review") is False


def test_three_infra_nacks_leave_fresh_seat_offerable(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _seed(home, SEAT_A)
    reasons = (
        (SEAT_A, "hard ceiling 1800000ms"),
        (SEAT_B, "worktree-create-failed:no-clone"),
        (SEAT_C, "holder_bored"),
    )
    for seat, reason in reasons:
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="FR",
            ident="#8375",
            now=time.time(),
            reason=reason,
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#8375"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert gitclaim.row_needs_human(final, FRESH) is False
    assert int(final.get("hard_ceiling_count") or 0) == 1
    st, offered = gitclaim.offer_focus_top(
        home, FRESH, "#marchhare", now=time.time() + 10_000
    )
    assert st == "ok" and offered["id"] == "#8375"


def test_product_giveup_still_stamps_needs_human_at_threshold(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    _seed(home, SEAT_A)
    for seat, reason in ((SEAT_A, "cannot review"), (SEAT_B, "blocked")):
        doc = gitclaim._load_queue_unlocked(home)
        doc = _accept(doc, seat)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, job = shop_listen.return_job_to_unaccepted(
            home,
            repo=REPO,
            task="FR",
            ident="#8375",
            now=time.time(),
            reason=reason,
        )
        assert st == "ok" and job is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#8375"][0]
    assert int(final.get("giveup_count") or 0) == 2
    assert final.get("needs_human") is True
    assert gitclaim.row_needs_human(final, FRESH) is True
