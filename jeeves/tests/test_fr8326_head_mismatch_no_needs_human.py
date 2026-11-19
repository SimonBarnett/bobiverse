"""FR #8326: head-mismatch NACKs do not stamp needs_human."""
from __future__ import annotations

import time

import bobreport
import gitclaim
import registered_machines
import shop_listen

REPO = "SimonBarnett/bobiverse"
SEAT_A = "flamingo-1104"
SEAT_B = "flamingo-12064"
FRESH = "marchhare-18680"
WANT = "a" * 40
HAVE = "b" * 40
REASON = f"worktree-create-failed:head-mismatch want={WANT} have={HAVE}"


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    registered_machines.save_registered(tmp_path, {"marchhare", "flamingo"})
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    digest = bobreport.empty_digest()
    for mid, workers in (
        ("flamingo", {"1104": {"state": "idle", "nick": SEAT_A}, "12064": {"state": "idle", "nick": SEAT_B}}),
        ("marchhare", {"18680": {"state": "idle", "nick": FRESH}}),
    ):
        digest["machines"][mid] = bobreport._empty_machine(mid)
        digest["machines"][mid]["workers"] = workers
    bobreport.save_digest(tmp_path, digest)
    return tmp_path


def test_fr8326_two_head_mismatch_nacks_do_not_need_human(tmp_path, monkeypatch):
    home = _home(tmp_path, monkeypatch)
    row = {
        "repo": REPO,
        "task": "MRB",
        "id": "#8299",
        "nick": SEAT_A,
        "seq": 1,
        "ts": "t",
        "line": "x",
        "url": f"https://github.com/{REPO}/pull/8299",
        "giveup_count": 0,
    }
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": [], "accepted": [dict(row)], "done": []},
    )
    for seat in (SEAT_A, SEAT_B):
        doc = gitclaim._load_queue_unlocked(home)
        un = [r for r in (doc.get("unaccepted") or []) if r.get("id") == "#8299"]
        job = dict(un[0]) if un else None
        if job is None:
            job = [r for r in doc.get("accepted") or [] if r.get("id") == "#8299"][0]
            doc["accepted"] = [r for r in doc["accepted"] if r.get("id") != "#8299"]
        else:
            doc["unaccepted"] = [r for r in doc["unaccepted"] if r.get("id") != "#8299"]
        job["nick"] = seat
        doc.setdefault("accepted", []).append(job)
        gitclaim._write_queue(gitclaim.queue_path(home), doc)
        st, out = shop_listen.return_job_to_unaccepted(
            home, repo=REPO, task="MRB", ident="#8299", now=time.time(), reason=REASON
        )
        assert st == "ok" and out is not None

    final = [r for r in gitclaim.load_unaccepted(home) if r.get("id") == "#8299"][0]
    assert int(final.get("giveup_count") or 0) == 0
    assert not final.get("needs_human")
    assert not str(final.get("giveup_seats") or "").strip()


def test_fr8326_heal_clears_stuck_needs_human():
    row = {
        "needs_human": True,
        "giveup_count": 2,
        "giveup_seats": "flamingo-1104,flamingo-12064",
        "cooldown_until": "2099-01-01T00:00:00Z",
        "giveup_reason": REASON,
    }
    assert gitclaim.heal_worktree_head_mismatch_row(row) is True
    assert not row.get("needs_human")
    assert int(row.get("giveup_count") or 0) == 0
    assert not row.get("giveup_seats")
    assert gitclaim.heal_worktree_head_mismatch_row({"giveup_reason": "cannot review", "needs_human": True}) is False
