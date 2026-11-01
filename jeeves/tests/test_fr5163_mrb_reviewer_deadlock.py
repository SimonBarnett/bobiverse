"""FR #5163: Jeeves resolves MRB reviewer deadlock (cross give-up / author-only).

When every idle seat is ineligible for every waiting MRB (author or give-up),
chair heals deterministically so an offer can proceed — no manual recycle /
!cleargiveup.
"""
from __future__ import annotations

import json
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import recycleseat


def _two_idle(tmp_path, monkeypatch, a="flamingo-67876", b="marchhare-22900"):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["flamingo"] = bobreport._empty_machine("flamingo")
    digest["machines"]["flamingo"]["worker_list"] = [
        {"nick": a, "state": "idle"}
    ]
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": b, "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    return a, b


def _mrb_row(*, repo, num, author, giveup="", **extra):
    row = {
        "repo": repo,
        "task": "MRB",
        "id": f"#{num}",
        "seq": int(num),
        "needs_human": False,
        "author_seat": author,
        "line": f"MRB {repo}#{num}",
        "url": f"https://github.com/{repo}/pull/{num}",
        "ts": "t",
        "event": "pull_request",
        "action": "opened",
    }
    if giveup:
        row["giveup_seats"] = giveup
        row["giveup_count"] = len([x for x in giveup.split(",") if x.strip()])
    row.update(extra)
    return row


def test_fr5163_cross_giveup_heal_then_offer(tmp_path, monkeypatch):
    """A authored X + gave up Y; B authored Y + gave up X → clear give-ups → offer."""
    a, b = _two_idle(tmp_path, monkeypatch)
    # X=#5294 authored by flamingo; Y=#5289 authored by marchhare
    doc = {
        "v": 1,
        "unaccepted": [
            _mrb_row(
                repo="SimonBarnett/a-search",
                num=5294,
                author=a,
                giveup=b,  # marchhare gave up flamingo's PR
            ),
            _mrb_row(
                repo="SimonBarnett/a-search",
                num=5289,
                author=b,
                giveup=a,  # flamingo gave up marchhare's PR
            ),
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)

    # Before heal: both seats see 0 offerable
    st_a, job_a = gitclaim.offer_focus_top(
        tmp_path, a, "#flamingo", pr_exists=lambda *a, **k: True
    )
    assert st_a == "ok", (st_a, job_a)
    # flamingo is author of 5294; after heal can take 5289 (cleared own give-up)
    assert job_a.get("id") in ("#5289", "#5294")
    assert job_a.get("offered_to") == a
    # Must not be self-MRB of 5294
    assert job_a.get("id") == "#5289"


def test_fr5163_author_only_queues_recycleseat(tmp_path, monkeypatch):
    """FR #5889: author-only flags MRBs; does not queue !recycleseat."""
    a, b = _two_idle(tmp_path, monkeypatch)
    both = f"{a},{b}"
    doc = {
        "v": 1,
        "unaccepted": [
            _mrb_row(
                repo="SimonBarnett/a-search",
                num=5294,
                author=a,
                **{"author_seats": both},
            ),
            _mrb_row(
                repo="SimonBarnett/a-search",
                num=5289,
                author=b,
                **{"author_seats": both},
            ),
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_000_000.0
    )
    assert lines, "expected heal lines"
    assert any("author_only" in x and "flag" in x.lower() for x in lines), lines
    assert not any("recycleseat=" in x for x in lines), lines
    qdir = recycleseat.queue_dir(install)
    assert list(qdir.glob("req-*.json")) == []
    saved = json.loads(gitclaim.queue_path(tmp_path).read_text(encoding="utf-8"))
    assert all(r.get("author_only_deadlock") for r in saved["unaccepted"])

    # Signature cooldown: second heal within window is a no-op
    lines2 = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_000_030.0
    )
    assert lines2 == []


def test_fr5163_no_heal_when_one_seat_eligible(tmp_path, monkeypatch):
    """Idle third-party seat can take a row → no deadlock heal."""
    a, b = _two_idle(tmp_path, monkeypatch, a="flamingo-1", b="marchhare-2")
    # Extra idle seat with no author/giveup
    digest = bobreport.load_digest(tmp_path)
    registered_machines.save_registered(tmp_path, {"flamingo", "marchhare", "ionos"})
    digest["machines"]["ionos"] = bobreport._empty_machine("ionos")
    digest["machines"]["ionos"]["worker_list"] = [
        {"nick": "ionos-9", "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    doc = {
        "v": 1,
        "unaccepted": [
            _mrb_row(repo="SimonBarnett/a-search", num=1, author="flamingo-1", giveup="marchhare-2"),
        ],
        "accepted": [],
        "done": [],
    }
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    install = tmp_path / "install"
    install.mkdir()
    lines = gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_000_000.0
    )
    assert lines == []
    assert list((install / "run" / "recycleseat").glob("req-*.json")) == []
    st, job = gitclaim.offer_focus_top(
        tmp_path, "ionos-9", "#ionos", pr_exists=lambda *a, **k: True
    )
    assert st == "ok"
    assert job.get("offered_to") == "ionos-9"


def test_fr5270_single_idle_giveup_not_cross_clear(tmp_path, monkeypatch):
    """Lone idle seat GIVEUP must not be healed as cross_giveup (FR #5270 / #5268)."""
    a = "marchhare-1"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [{"nick": a, "state": "idle"}]
    bobreport.save_digest(tmp_path, digest)
    row = _mrb_row(repo="SimonBarnett/bobiverse", num=1, author="", giveup=a)
    row.pop("author_seat", None)
    doc = {"v": 1, "unaccepted": [row], "accepted": [], "done": []}
    gitclaim._write_queue(gitclaim.queue_path(tmp_path), doc)
    live = gitclaim.live_seat_nicks(tmp_path)
    idle = gitclaim.free_seat_nicks(tmp_path, live)
    assert idle == {a}
    info = gitclaim.detect_mrb_reviewer_deadlock(
        tmp_path, idle=idle, live=live, rows=doc["unaccepted"]
    )
    # Main FR #5268: sole-seat giveup is not author_only recycleseat (return None).
    assert info is None
    gitclaim.heal_mrb_reviewer_deadlock(tmp_path, idle=idle, live=live)
    kept = gitclaim.load_queue(tmp_path)["unaccepted"][0]
    assert a in str(kept.get("giveup_seats") or "")
    st, job = gitclaim.offer_focus_top(tmp_path, a, "#marchhare", now=1000.0)
    assert st == "empty" and job is None


def test_fr5268_sole_idle_giveup_not_cleared(tmp_path, monkeypatch):
    """FR #5268: one idle seat that GIVEUP'd the only MRB must keep giveup_seats.

    Before the fix, detect_mrb_reviewer_deadlock treated this as cross_giveup,
    heal cleared the stamp, and offer_focus_top re-offered the same job.
    """
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    nick = "marchhare-1"
    registered_machines.save_registered(tmp_path, {"marchhare"})
    digest = bobreport.empty_digest()
    digest["machines"]["marchhare"] = bobreport._empty_machine("marchhare")
    digest["machines"]["marchhare"]["worker_list"] = [
        {"nick": nick, "state": "idle"}
    ]
    bobreport.save_digest(tmp_path, digest)
    row = _mrb_row(
        repo="SimonBarnett/bobiverse",
        num=1,
        author="flamingo-99",
        giveup=nick,
    )
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [row], "accepted": [], "done": []},
    )
    live = gitclaim.live_seat_nicks(tmp_path)
    free = gitclaim.free_seat_nicks(tmp_path, live)
    assert free == {nick}
    assert gitclaim.detect_mrb_reviewer_deadlock(
        tmp_path, idle=free, live=live
    ) is None
    install = tmp_path / "install"
    install.mkdir()
    assert gitclaim.heal_mrb_reviewer_deadlock(
        tmp_path, install_root=install, now=1_000_000.0
    ) == []
    kept = gitclaim.load_queue(tmp_path)["unaccepted"][0]
    assert nick in str(kept.get("giveup_seats") or "")
    st, job = gitclaim.offer_focus_top(
        tmp_path, nick, "#marchhare", pr_exists=lambda *a, **k: True
    )
    assert st == "empty" and job is None
    after = gitclaim.load_queue(tmp_path)["unaccepted"][0]
    assert nick in str(after.get("giveup_seats") or "")
