"""FR #8195: accepted_silent sweep keeps jobs with fresh digest last_progress.

While a seat runs a long silent tool (e.g. pytest buffered by Out-String), IRC
activity goes quiet. Heartbeats must keep digest last_progress fresh, and the
stuck sweep must treat that as activity so LOST_ACK_RESTART is not fired.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bobreport
import gitclaim
import registered_machines
import stuck_job_sweep as sweep


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue(home: Path, *, accepted=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": [],
        "accepted": list(accepted or []),
        "done": [],
    }
    gitclaim.queue_path(home).write_text(json.dumps(doc), encoding="utf-8")


def _digest_doing(
    home: Path,
    *,
    nick: str = "redqueen-1400",
    mid: str = "redqueen",
    last_progress: str = "",
    work: str = "FR SimonBarnett/bobiverse#8138",
) -> None:
    registered_machines.save_registered(home, {mid, "flamingo", "ionos"})
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    row = {
        "nick": nick,
        "state": "doing",
        "work": work,
        "kind": "grok",
        "updated": last_progress or _iso(1_700_000_000.0),
    }
    if last_progress:
        row["last_progress"] = last_progress
        row["progress_phase"] = "tool:alive"
    digest["machines"][mid]["worker_list"] = [row]
    bobreport.save_digest(home, digest)


def test_fr8195_fresh_last_progress_blocks_accepted_silent_release(tmp_path: Path, monkeypatch):
    """Live heartbeat (fresh last_progress) past the old silence window → keep ACK."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    now = 1_700_000_000.0
    nick = "redqueen-1400"
    # Accepted ~33 min ago; IRC activity equally stale (would release under #5510).
    accepted_ts = _iso(now - 2000.0)
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8138",
                "nick": nick,
                "accepted_ts": accepted_ts,
                "line": "FR SimonBarnett/bobiverse#8138",
            }
        ],
    )
    # Digest heartbeat only 60s ago while a long tool runs.
    _digest_doing(home, nick=nick, last_progress=_iso(now - 60.0))
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={nick},
        idle=set(),
        activity={nick: now - 2000.0},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 0
    doc = gitclaim.load_queue(home)
    assert len(doc["accepted"]) == 1
    assert doc["accepted"][0]["id"] in ("#8138", "8138") or str(doc["accepted"][0]["id"]).endswith("8138")


def test_fr8195_stale_last_progress_still_releases(tmp_path: Path, monkeypatch):
    """Heartbeat older than SILENT_ACCEPTED_S → release as today."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    now = 1_700_000_000.0
    nick = "redqueen-1400"
    accepted_ts = _iso(now - 2000.0)
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8138",
                "nick": nick,
                "accepted_ts": accepted_ts,
                "line": "FR SimonBarnett/bobiverse#8138",
            }
        ],
    )
    _digest_doing(home, nick=nick, last_progress=_iso(now - 2000.0))
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live={nick},
        idle=set(),
        activity={nick: now - 2000.0},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] == 1
    doc = gitclaim.load_queue(home)
    assert doc["accepted"] == []
    assert any(str(r.get("id")).endswith("8138") for r in doc["unaccepted"])


def test_fr8195_digest_progress_epoch_helper(tmp_path: Path, monkeypatch):
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    now = 1_700_000_000.0
    _digest_doing(home, nick="flamingo-99", mid="flamingo", last_progress=_iso(now - 12.0))
    ts = sweep.digest_holder_last_progress_epoch(home, "flamingo-99")
    assert ts is not None
    assert abs(float(ts) - (now - 12.0)) < 1.5
    assert sweep.digest_holder_last_progress_epoch(home, "missing-1") is None
