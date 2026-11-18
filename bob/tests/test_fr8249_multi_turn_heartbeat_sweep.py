# -*- coding: utf-8 -*-
"""FR #8249: multi-turn heartbeats keep accepted_silent from releasing a live seat."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bob_worker as bw
import bobreport
import gitclaim
import registered_machines
import stuck_job_sweep as sweep
from test_fr2802_bored_on_turn_end import FakeClock, _emitter
from test_fr8249_heartbeat_own_timer import FakeIrc, FakeProc, FakeRelay, _capture_posts, _force_tick


def _iso(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _queue(home: Path, *, accepted=None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    doc = {
        "unaccepted": [],
        "accepted": list(accepted or []),
        "done": [],
    }
    gitclaim.queue_path(home).write_text(
        __import__("json").dumps(doc), encoding="utf-8"
    )


def _seed_digest(home: Path, *, mid: str, nick: str) -> None:
    registered_machines.save_registered(home, {mid, "flamingo", "ionos"})
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["worker_list"] = [
        {
            "nick": nick,
            "state": "idle",
            "work": "",
            "kind": "opencode",
            "updated": _iso(1_700_000_000.0),
        }
    ]
    bobreport.save_digest(home, digest)


def test_fr8249_multi_turn_heartbeats_block_accepted_silent(monkeypatch, tmp_path):
    """50+ minutes of turns/FINISH gaps with fresh last_progress → no release."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    mid, nick = "redqueen", "redqueen-7968"
    work = "FR SimonBarnett/bobiverse#8249"
    now0 = 1_700_000_000.0
    accepted_ts = _iso(now0 - 2000.0)
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8249",
                "nick": nick,
                "accepted_ts": accepted_ts,
                "line": work,
            }
        ],
    )
    _seed_digest(home, mid=mid, nick=nick)

    posts = _capture_posts(monkeypatch)
    clock = FakeClock(now0)
    e, _sent, logs = _emitter(clock, done_miss_grace_s=5.0)
    reminds: list[str] = []
    e.done_miss_remind_fn = lambda k: reminds.append(k)

    # Controlled wall ISO for digest last_progress.
    wall = {"t": now0}

    def _utc():
        return _iso(wall["t"])

    monkeypatch.setattr(bobreport, "_utc_now_iso", _utc)

    try:
        sup = bw.Supervisor(
            kind="opencode",
            exe="x",
            cwd=str(tmp_path / "cwd"),
            machine=mid,
            nick=nick,
            run_dir=tmp_path / "run",
            irc=FakeIrc(),
            relay=FakeRelay(),
            log=logs.append,
            bored=e,
            clock=clock,
            startup_grace_s=0.0,
            backoff=(0.0,),
            kill=lambda pid: True,
            spawn=lambda spec, env: FakeProc(),
            health_interval_s=60.0,
        )
        (tmp_path / "run").mkdir(parents=True, exist_ok=True)
        (tmp_path / "cwd").mkdir(parents=True, exist_ok=True)
        sup.proc = FakeProc(pid=7968)

        e.on_outbox(f"ACK {work}")

        # Drive ~55 minutes with turn gaps and FINISH reminder; apply each POST to digest.
        elapsed = 0.0
        while elapsed < 3300.0:
            wall["t"] = now0 + elapsed
            clock.t = now0 + elapsed
            if int(elapsed) % 600 == 120:
                e.turn_started(at=clock())
            if int(elapsed) % 600 == 180:
                e.turn_ended(at=clock())
            if int(elapsed) == 900:
                # Simulate FINISH / done-miss reminder between turns.
                reminds.append(work)

            n_before = len(posts)
            _force_tick(sup, clock)
            if len(posts) > n_before:
                payload = dict(posts[-1])
                # Forward through digest apply (same path as bobcallback handle_report_post).
                out = bobreport.apply_callback(home, payload)
                assert out.ok, payload

            # Active sweep every 10 minutes with nick live + stale IRC activity.
            if int(elapsed) % 600 == 0 and elapsed > 0:
                report = sweep.run_stuck_sweep(
                    home,
                    now=now0 + elapsed,
                    live={nick},
                    idle=set(),
                    activity={nick: now0 - 2000.0},
                    open_items=[],
                    act=True,
                )
                assert report["actions"]["released"] == 0, (
                    f"released at t+{elapsed}s last_progress={posts[-1].get('last_progress') if posts else None}"
                )
                doc = gitclaim.load_queue(home)
                assert len(doc["accepted"]) == 1

            elapsed += 30.0  # heartbeat cadence floor

        doc = gitclaim.load_queue(home)
        assert len(doc["accepted"]) == 1
        assert posts
        assert all(p.get("work") == work for p in posts)
        # Digest must carry a fresh last_progress near the end.
        row = None
        digest = bobreport.load_digest(home)
        for w in digest["machines"][mid].get("worker_list") or []:
            if w.get("nick") == nick:
                row = w
                break
        assert row is not None
        assert row.get("last_progress")
        assert row.get("state") == "doing"
    finally:
        e.stop()


def test_fr8249_negative_stale_still_releases(monkeypatch, tmp_path):
    """Negative control: stale last_progress still triggers accepted_silent."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    mid, nick = "redqueen", "redqueen-7968"
    now = 1_700_000_000.0
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8249",
                "nick": nick,
                "accepted_ts": _iso(now - 2000.0),
                "line": "FR SimonBarnett/bobiverse#8249",
            }
        ],
    )
    registered_machines.save_registered(home, {mid, "flamingo", "ionos"})
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["worker_list"] = [
        {
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8249",
            "kind": "opencode",
            "updated": _iso(now - 2000.0),
            "last_progress": _iso(now - 2000.0),
            "progress_phase": "tool:alive",
        }
    ]
    bobreport.save_digest(home, digest)
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


def test_fr8249_negative_holder_gone_still_releases(monkeypatch, tmp_path):
    """Negative control: holder not live → accepted_holder_gone path still releases."""
    home = tmp_path / "digest"
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    mid, nick = "redqueen", "redqueen-7968"
    now = 1_700_000_000.0
    _queue(
        home,
        accepted=[
            {
                "repo": "SimonBarnett/bobiverse",
                "task": "FR",
                "id": "#8249",
                "nick": nick,
                "accepted_ts": _iso(now - 2000.0),
                "line": "FR SimonBarnett/bobiverse#8249",
            }
        ],
    )
    registered_machines.save_registered(home, {mid, "flamingo", "ionos"})
    if hasattr(bobreport, "_SEAT_ROSTER_CACHE"):
        bobreport._SEAT_ROSTER_CACHE["key"] = None
        bobreport._SEAT_ROSTER_CACHE["ids"] = ()
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["worker_list"] = [
        {
            "nick": nick,
            "state": "doing",
            "work": "FR SimonBarnett/bobiverse#8249",
            "kind": "opencode",
            "updated": _iso(now - 60.0),
            "last_progress": _iso(now - 60.0),
            "progress_phase": "tool:alive",
        }
    ]
    bobreport.save_digest(home, digest)
    report = sweep.run_stuck_sweep(
        home,
        now=now,
        live=set(),  # holder gone
        idle=set(),
        activity={},
        open_items=[],
        act=True,
    )
    assert report["actions"]["released"] >= 1
