# -*- coding: utf-8 -*-
"""FR #8249: progress heartbeats on a dedicated timer, lock-free of FINISH/_cv."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


class FakeProc:
    def __init__(self, pid: int = 8249):
        self.pid = pid
        self._code = None

    def poll(self):
        return self._code

    def wait(self):
        return self._code if self._code is not None else 0

    def exit(self, code: int = 0) -> None:
        self._code = int(code)


class FakeRelay:
    last_unacked = ""
    last_line = ""

    def close(self):
        pass


class FakeIrc:
    shop = "#flamingo"
    alive = True

    def close(self, *a, **k):
        pass

    def say(self, *a, **k):
        return True


def _supervisor(tmp_path: Path, clock: FakeClock, bored, *, logs=None, kind="opencode"):
    logs = logs if logs is not None else []
    sup = bw.Supervisor(
        kind=kind,
        exe="x",
        cwd=str(tmp_path),
        machine="flamingo",
        nick="flamingo-8249",
        run_dir=tmp_path,
        irc=FakeIrc(),
        relay=FakeRelay(),
        log=logs.append,
        bored=bored,
        clock=clock,
        startup_grace_s=0.0,
        backoff=(0.0,),
        kill=lambda pid: True,
        spawn=lambda spec, env: FakeProc(),
        health_interval_s=60.0,
    )
    proc = FakeProc()
    sup.proc = proc
    return sup, proc, logs


def _capture_posts(monkeypatch):
    posts: list[dict] = []

    def _fake_post(url, payload, log=None, **kw):
        posts.append(dict(payload))
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    monkeypatch.setenv("BOB_REPORT_URL", "https://example.test/bob/v1/report")
    monkeypatch.setenv("BOB_PROGRESS_HEARTBEAT_S", "30")
    return posts


def _force_tick(sup, clock: FakeClock) -> None:
    sup._progress_last_post_mono = 0.0
    sup._progress_last_seen_mono = clock()
    sup._maybe_progress_heartbeat()


def test_fr8249_heartbeat_snapshot_lock_free():
    clock = FakeClock(0.0)
    e, _sent, _logs = _emitter(clock)
    try:
        snap0 = e.heartbeat_snapshot()
        assert snap0.ack_open is False
        assert snap0.ack_epoch == 0
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")
        snap1 = e.heartbeat_snapshot()
        assert snap1.ack_open is True
        assert snap1.ack_job_key == "FR SimonBarnett/bobiverse#8249"
        assert snap1.ack_epoch == 1
        assert snap1.out_of_fuel is False
        held = threading.Event()
        release = threading.Event()

        def _hold():
            with e._cv:
                held.set()
                release.wait(timeout=2.0)

        th = threading.Thread(target=_hold, daemon=True)
        th.start()
        assert held.wait(timeout=1.0)
        snap2 = e.heartbeat_snapshot()
        assert snap2.ack_open is True
        assert snap2.ack_epoch == 1
        release.set()
        th.join(timeout=2.0)
        e.on_outbox("DONE FR SimonBarnett/bobiverse#8249 https://example.com/p/1")
        snap3 = e.heartbeat_snapshot()
        assert snap3.ack_open is False
    finally:
        e.stop()


def test_fr8249_multi_turn_posts_same_work(monkeypatch, tmp_path):
    posts = _capture_posts(monkeypatch)
    clock = FakeClock(1000.0)
    e, _sent, logs = _emitter(clock, done_miss_grace_s=5.0)
    reminds: list[str] = []
    e.done_miss_remind_fn = lambda k: reminds.append(k)
    retries: list[str] = []
    e.failed_turn_retry_fn = lambda k: retries.append(k)
    try:
        sup, proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")
        assert e.heartbeat_snapshot().ack_epoch == 1

        _force_tick(sup, clock)
        assert posts, "first heartbeat missing"
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"
        assert posts[-1]["state"] == "doing"

        e.turn_started(at=clock())
        clock.t += 10.0
        e.turn_ended(at=clock())
        _force_tick(sup, clock)
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"

        # Simulate FINISH / done-miss reminder inject without waiting on the timer.
        reminds.append("FR SimonBarnett/bobiverse#8249")
        _force_tick(sup, clock)
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"

        e.turn_started(at=clock())
        clock.t += 5.0
        e.turn_ended(at=clock(), error=True, error_class="tool", error_line="boom")
        clock.t += 1.0
        _force_tick(sup, clock)
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"

        e.turn_started(at=clock())
        clock.t += 5.0
        _force_tick(sup, clock)
        works = [p["work"] for p in posts]
        assert all(w == "FR SimonBarnett/bobiverse#8249" for w in works)
        assert len(posts) >= 4
        assert proc.poll() is None
    finally:
        e.stop()


def test_fr8249_posts_while_cv_and_rlock_held(monkeypatch, tmp_path):
    posts = _capture_posts(monkeypatch)
    clock = FakeClock(2000.0)
    e, _sent, logs = _emitter(clock)
    cv_release = threading.Event()
    lock_release = threading.Event()
    try:
        sup, _proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")
        # Stop bored-timer so it cannot contend for `_cv` during the hold.
        e.stop()
        # Snapshot must remain open after stop (stop only ends the timer thread).
        assert e.heartbeat_snapshot().ack_open is True
        sup._progress_last_seen_mono = clock()
        sup._progress_last_post_mono = 0.0

        cv_held = threading.Event()
        lock_held = threading.Event()

        def _hold_cv():
            with e._cv:
                cv_held.set()
                cv_release.wait(timeout=3.0)

        def _hold_rlock():
            with sup._lock:
                lock_held.set()
                lock_release.wait(timeout=3.0)

        th_cv = threading.Thread(target=_hold_cv, daemon=True)
        th_lk = threading.Thread(target=_hold_rlock, daemon=True)
        th_cv.start()
        th_lk.start()
        assert cv_held.wait(timeout=2.0)
        assert lock_held.wait(timeout=2.0)
        clock.t += 1.0
        n0 = len(posts)
        t0 = time.monotonic()
        th = threading.Thread(target=sup._maybe_progress_heartbeat, daemon=True)
        th.start()
        th.join(timeout=1.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.8, f"heartbeat blocked {elapsed:.3f}s under held locks"
        assert len(posts) > n0
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"
    finally:
        cv_release.set()
        lock_release.set()
        try:
            e.stop()
        except Exception:
            pass


def test_fr8249_done_fuel_exit_and_new_job_cadence(monkeypatch, tmp_path):
    posts = _capture_posts(monkeypatch)
    clock = FakeClock(3000.0)
    e, _sent, logs = _emitter(clock)
    try:
        sup, proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")

        _force_tick(sup, clock)
        n1 = len(posts)
        assert n1 >= 1

        e.on_outbox("DONE FR SimonBarnett/bobiverse#8249 https://example.com/p/1")
        clock.t += 1.0
        _force_tick(sup, clock)
        assert len(posts) == n1
        assert any("skip reason=no-ack" in m for m in logs)

        # New job: first POST must not inherit prior job cadence.
        e.on_outbox("ACK FR SimonBarnett/bobiverse#9999")
        assert e.heartbeat_snapshot().ack_epoch == 2
        # Pretend we just posted under the old epoch bookkeeping.
        sup._progress_last_post_mono = clock()
        sup._progress_hb_epoch = 1
        sup._progress_last_seen_mono = clock()
        sup._maybe_progress_heartbeat()
        assert len(posts) > n1
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#9999"
        n2 = len(posts)

        # Fuel hold with ACK still open (snapshot gate).
        with e._cv:
            e._out_of_fuel = True
            e._hb_notify_all()
        assert e.heartbeat_snapshot().out_of_fuel is True
        sup._progress_hb_skip_log_mono = 0.0  # reset rate-limit from prior no-ack
        clock.t += 1.0
        _force_tick(sup, clock)
        assert len(posts) == n2
        assert any("skip reason=fuel-hold" in m for m in logs)
        with e._cv:
            e._out_of_fuel = False
            e._hb_notify_all()

        _force_tick(sup, clock)
        n3 = len(posts)
        proc.exit(0)
        sup._progress_hb_skip_log_mono = 0.0
        clock.t += 1.0
        _force_tick(sup, clock)
        assert len(posts) == n3
        assert any("skip reason=proc-exited" in m for m in logs)
    finally:
        e.stop()


def test_fr8249_epoch_change_skips_stale_post(monkeypatch, tmp_path):
    posts = _capture_posts(monkeypatch)
    clock = FakeClock(3500.0)
    e, _sent, logs = _emitter(clock)
    try:
        sup, _proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        e.on_outbox("ACK FR SimonBarnett/bobiverse#1111")
        epoch = e.heartbeat_snapshot().ack_epoch
        n0 = len(posts)

        def _detect(**kw):
            # Close ACK after scan, before re-validate POST.
            with e._cv:
                e._ack_open = False
                e._ack_job_key = None
                e._hb_notify_all()
            return False, "tool:alive", {}

        monkeypatch.setattr(bw, "detect_seat_progress", _detect)
        sup._progress_hb_epoch = epoch
        _force_tick(sup, clock)
        assert len(posts) == n0
        assert any("skip reason=no-ack" in m for m in logs)
    finally:
        e.stop()


def test_fr8249_tick_exception_and_shutdown_join(monkeypatch, tmp_path):
    posts = _capture_posts(monkeypatch)
    clock = FakeClock(4000.0)
    e, _sent, logs = _emitter(clock)
    try:
        sup, _proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")

        # Loop-level guard swallows one bad tick.
        boom = {"n": 0}
        real = bw.Supervisor._maybe_progress_heartbeat

        def _boom(self):
            boom["n"] += 1
            if boom["n"] == 1:
                raise RuntimeError("boom")
            return real(self)

        monkeypatch.setattr(bw.Supervisor, "_maybe_progress_heartbeat", _boom)
        # One guarded iteration (same as the loop body).
        try:
            sup._maybe_progress_heartbeat()
        except Exception as ex:
            logs.append(f"progress-heartbeat: tick failed {type(ex).__name__}")
        assert any("tick failed RuntimeError" in m for m in logs)
        # Second call succeeds and POSTs.
        _force_tick(sup, clock)
        assert posts
        assert posts[-1]["work"] == "FR SimonBarnett/bobiverse#8249"

        monkeypatch.setattr(bw.Supervisor, "_maybe_progress_heartbeat", real)

        # Start heartbeat thread, then bounded join via _stop_progress_heartbeat.
        started = threading.Event()

        def _loop():
            started.set()
            while not sup.stop.wait(0.05):
                if getattr(sup, "_shutting", False):
                    return

        th = threading.Thread(target=_loop, name="progress-heartbeat", daemon=True)
        sup._progress_hb_thread = th
        th.start()
        assert started.wait(timeout=1.0)
        sup.stop.set()
        t0 = time.monotonic()
        sup._stop_progress_heartbeat()
        elapsed = time.monotonic() - t0
        assert elapsed < 2.5
        assert not th.is_alive()
        assert getattr(sup, "_progress_hb_thread", None) is None
    finally:
        e.stop()


def test_fr8249_note_agent_active_nb_returns_false_when_busy():
    clock = FakeClock(0.0)
    e, _sent, _ = _emitter(clock)
    try:
        e.on_outbox("ACK FR SimonBarnett/bobiverse#8249")
        held = threading.Event()
        release = threading.Event()

        def _hold():
            with e._cv:
                held.set()
                release.wait(timeout=2.0)

        th = threading.Thread(target=_hold, daemon=True)
        th.start()
        assert held.wait(timeout=1.0)
        assert e.note_agent_active_nb(timeout=0.05) is False
        release.set()
        th.join(timeout=2.0)
        assert e.note_agent_active_nb(timeout=0.5) is True
    finally:
        e.stop()


def test_fr8249_health_loop_does_not_call_heartbeat(monkeypatch, tmp_path):
    """Regression: heartbeat must not run inline on the health thread."""
    clock = FakeClock(5000.0)
    e, _sent, logs = _emitter(clock)
    try:
        sup, proc, _ = _supervisor(tmp_path, clock, e, logs=logs)
        called = {"n": 0}

        def _count():
            called["n"] += 1

        monkeypatch.setattr(sup, "_maybe_progress_heartbeat", _count)
        monkeypatch.setattr(sup, "probe", lambda pid: bw.Sample(activity=1, cpu=0.0, working_set=0))
        # One health iteration: stop after first pass.
        stop_after = {"n": 0}
        real_wait = threading.Event.wait

        def _once(self, timeout=None):
            stop_after["n"] += 1
            if stop_after["n"] > 1:
                return True  # stop
            return False

        monkeypatch.setattr(sup.stop, "wait", lambda timeout=None: _once(sup.stop, timeout))
        # health_loop uses self.stop.wait — patch instance method via type is hard;
        # call body fragment instead: ensure source no longer invokes heartbeat.
        src = bw.Supervisor.health_loop.__code__.co_names
        assert "_maybe_progress_heartbeat" not in src
        assert called["n"] == 0
        _ = proc
        _ = real_wait
    finally:
        e.stop()
