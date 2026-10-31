"""FR #5581: PASS on CONFLICTING clears doing + queues FIX; stuck sweep clears verdicted doing >15m."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bobreport
import gitclaim
import mrb_merge_on_green
import shop_listen
import stuck_job_sweep as sweep

PASS_SHA = "a" * 40
REPO = "SimonBarnett/bobiverse"
PR = "5545"
NICK = "flamingo-15400"
MID = "flamingo"


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _roster(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": [MID]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_doing(home: Path, *, updated: str, work: str = f"bobiverse MRB #{PR}") -> None:
    doc = bobreport.empty_digest()
    doc["machines"][MID] = {
        "id": MID,
        "online": True,
        "working_on": work,
        "worker_list": [
            {
                "nick": NICK,
                "state": "doing",
                "work": work,
                "updated": updated,
            }
        ],
        "workers": {
            "15400": {
                "pid": "15400",
                "nick": NICK,
                "state": "doing",
                "working_on": work,
            }
        },
    }
    bobreport.save_digest(home, doc)


def _queue(home: Path, *, accepted=None, unaccepted=None, done=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    gitclaim.queue_path(home).write_text(
        json.dumps(
            {
                "unaccepted": list(unaccepted or []),
                "accepted": list(accepted or []),
                "done": list(done or []),
            }
        ),
        encoding="utf-8",
    )


def test_fr5581_enqueue_from_done_conflicting_offers_fix(tmp_path: Path):
    """PASS DONE on a CONFLICTING PR queues one conflict FIX immediately (no wait for merge sweep)."""
    home = tmp_path / "home"
    home.mkdir()

    def fetch_pr(repo, pr, **_k):
        return {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
            "merged": False,
            "closed": False,
            "checks": "success",
        }

    row = mrb_merge_on_green.enqueue_from_done(
        home,
        repo=REPO,
        pr_url=f"https://github.com/{REPO}/pull/{PR}",
        result="PASS",
        nick=NICK,
        fetch_pr=fetch_pr,
        fetch_comments=lambda *_a, **_k: [],
    )
    assert row is not None
    assert row.get("conflict_reason") in ("conflicting", "dirty") or str(
        row.get("conflict_fix") or ""
    ) in ("added", "duplicate", "reoffer")
    q = gitclaim.load_queue(home)
    fixes = [
        r
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict) and str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id") or "").lstrip("#") == PR
    ]
    assert fixes, "expected a FIX row for the CONFLICTING PR"
    # Do not leave a merge-pending row that will keep retrying merge forever.
    pending = mrb_merge_on_green.load_ledger(home).get("pending") or []
    assert not any(
        isinstance(p, dict) and str(p.get("pr") or "") == PR for p in pending
    )


def test_fr5581_done_pass_conflicting_clears_doing(tmp_path, monkeypatch):
    """DONE MRB PASS on CONFLICTING: FIX queued, seat activity idle, worker_list cleared."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    _digest_doing(home, updated="2026-10-31T20:59:16Z")
    _queue(
        home,
        accepted=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": f"#{PR}",
                "nick": NICK,
                "accepted_ts": "2026-10-31T20:50:00Z",
                "url": f"https://github.com/{REPO}/pull/{PR}",
                "line": f"MRB {REPO}#{PR}",
            }
        ],
    )

    def fetch_pr(repo, pr, **_k):
        return {
            "sha": PASS_SHA,
            "labels": [],
            "title": "tip",
            "body": "",
            "html_url": f"https://github.com/{REPO}/pull/{PR}",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
            "merged": False,
            "closed": False,
            "checks": "success",
        }

    monkeypatch.setattr(
        mrb_merge_on_green, "fetch_pr_state", lambda *a, **k: fetch_pr(*a, **k)
    )

    result = shop_listen.handle_shop_worker_line(
        home,
        nick=NICK,
        channel=f"#{MID}",
        body=(
            f"DONE MRB {REPO}#{PR} PASS "
            f"https://github.com/{REPO}/pull/{PR}"
        ),
        post_fn=lambda _p: 204,
    )
    assert result.get("handled")
    assert result.get("status") in ("ok", "duplicate")
    mog = result.get("merge_on_green") or {}
    assert mog.get("conflict_fix") in ("added", "duplicate", "reoffer") or mog.get(
        "conflict_reason"
    )
    d2 = bobreport.load_digest(home)
    wl = ((d2.get("machines") or {}).get(MID) or {}).get("worker_list") or []
    assert wl, "worker_list should still exist"
    assert wl[0].get("state") == "idle"
    assert not str(wl[0].get("work") or "").strip()
    assert gitclaim.worker_working_on(home, NICK) == ""
    q = gitclaim.load_queue(home)
    assert any(
        str(r.get("task") or "").upper() == "FIX"
        and str(r.get("id") or "").lstrip("#") == PR
        for r in (q.get("unaccepted") or [])
        if isinstance(r, dict)
    )


def test_fr5581_stuck_sweep_clears_verdicted_doing_after_15m(tmp_path, monkeypatch):
    """Doing tile with MRB already verdicted (done[] PASS) and updated >15m → clear."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    now = 1_700_000_000.0
    stale = _iso(now - 1000.0)  # ~16.6 min
    _digest_doing(home, updated=stale)
    _queue(
        home,
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": f"#{PR}",
                "result": "PASS",
                "done_by": NICK,
                "done_ts": _iso(now - 1100.0),
                "url": f"https://github.com/{REPO}/pull/{PR}",
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={NICK, "redqueen-1"},
        idle={"redqueen-1"},
        activity={NICK: now - 1000.0, "redqueen-1": now},
        open_items=[],
        act=True,
        fuel_ok=True,
    )
    assert int(report["actions"].get("cleared_doing") or 0) >= 1
    d2 = bobreport.load_digest(home)
    wl = ((d2.get("machines") or {}).get(MID) or {}).get("worker_list") or []
    assert wl[0].get("state") == "idle"
    assert not str(wl[0].get("work") or "").strip()


def test_fr5581_stuck_sweep_fresh_verdicted_doing_untouched(tmp_path, monkeypatch):
    """Verdicted doing updated <15m ago stays (seat may still be wrapping up)."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    now = 1_700_000_000.0
    fresh = _iso(now - 120.0)
    _digest_doing(home, updated=fresh)
    _queue(
        home,
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": f"#{PR}",
                "result": "PASS",
                "done_by": NICK,
                "done_ts": fresh,
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={NICK},
        idle=set(),
        activity={NICK: now - 120.0},
        open_items=[],
        act=True,
        fuel_ok=True,
    )
    assert int(report["actions"].get("cleared_doing") or 0) == 0
    d2 = bobreport.load_digest(home)
    wl = ((d2.get("machines") or {}).get(MID) or {}).get("worker_list") or []
    assert wl[0].get("state") == "doing"


def test_fr5581_stuck_sweep_pause_still_clears_verdicted_doing(tmp_path, monkeypatch):
    """no-seats/no-fuel pause suppresses alerts but still clears stale verdicted doing (bookkeeping)."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    now = 1_700_000_000.0
    _digest_doing(home, updated=_iso(now - 2000.0))
    _queue(
        home,
        done=[
            {
                "repo": REPO,
                "task": "MRB",
                "id": f"#{PR}",
                "result": "PASS",
                "done_by": NICK,
                "done_ts": _iso(now - 2100.0),
            }
        ],
    )
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),  # no seats → paused
        idle=set(),
        activity={},
        open_items=[],
        act=True,
        fuel_ok=True,
    )
    assert report.get("paused") == "no seats"
    assert report.get("stuck") == []
    assert int(report["actions"].get("cleared_doing") or 0) >= 1
    d2 = bobreport.load_digest(home)
    wl = ((d2.get("machines") or {}).get(MID) or {}).get("worker_list") or []
    assert wl[0].get("state") == "idle"
