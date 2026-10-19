"""FR #4732: submit-verify must not GIVEUP when the paste landed and the agent is working.

Cursor seats ACK on receipt, so job-matched ACK must not stop verify. A running
turn (or a late probe hit) during verify / a short pre-GIVEUP grace must.
"""
from __future__ import annotations

import bob_worker as bw
from test_fr4510_cursor_submit_verify_giveup import ASSIGN, GIVEUP, _cursor_recovery


def test_verify_loop_stops_when_turn_opens_even_if_probe_stays_false():
    """Fail-when: probe never sees prompt_history but turn_open means paste landed."""
    clock = {"t": 0.0}
    state = {"turn": False, "enters": 0}

    def enter():
        state["enters"] += 1
        # After first miss, the agent turn starts (paste had landed).
        state["turn"] = True
        return True

    def probe():
        return False

    def stop():
        return bool(state["turn"])

    def sleep(dt):
        clock["t"] += float(dt)

    res = bw.run_submit_verify_loop(
        enter_fn=enter,
        probe_fn=probe,
        clock=lambda: clock["t"],
        sleep=sleep,
        log=lambda m: None,
        verify_s=0.05,
        max_retries=2,
        backoffs=(0.05, 0.05),
        stop_fn=stop,
        t0=0.0,
    )
    assert res == "stop"
    assert state["enters"] >= 1


def test_cursor_giveup_grace_skips_when_turn_starts():
    """Fail-when: second failure must not queue GIVEUP if turn_running flips in grace."""
    running = {"v": False}
    ticks = {"n": 0}

    def turn_running():
        ticks["n"] += 1
        if ticks["n"] >= 3:
            running["v"] = True
        return bool(running["v"])

    sleeps: list[float] = []

    rec, state = _cursor_recovery(
        reinject=lambda line, cb: (cb(), True)[1],
        acked=True,
        running=turn_running,
    )
    # Patch grace helpers used by on_failed.
    old_grace = getattr(bw, "_submit_verify_giveup_grace_s", None)
    old_sleep = bw.time.sleep
    try:
        bw._submit_verify_giveup_grace_s = lambda default=20.0: 0.3  # type: ignore
        bw.time.sleep = lambda s: sleeps.append(float(s))
        assert rec.on_failed(ASSIGN, attempt=1) == "retried"
        assert state["outbox"] == []
        # attempt 2 path via reinject callback already fired; call final path directly
        # Reset closed set by using a fresh recovery for the grace branch.
    finally:
        if old_grace is None and hasattr(bw, "_submit_verify_giveup_grace_s"):
            # leave for product; tests set it
            pass
        bw.time.sleep = old_sleep

    # Dedicated recovery: reinject fails immediately so we hit giveup path with grace.
    def reinject_fail(line, cb):
        return False

    rec2, state2 = _cursor_recovery(
        reinject=reinject_fail,
        acked=True,
        running=turn_running,
    )
    ticks["n"] = 0
    running["v"] = False
    sleeps.clear()
    old_sleep = bw.time.sleep
    try:
        bw._submit_verify_giveup_grace_s = lambda default=20.0: 1.0  # type: ignore
        def _sleep(s):
            sleeps.append(float(s))
            # advance fake poll by flipping after a couple sleeps
            if len(sleeps) >= 2:
                running["v"] = True
        bw.time.sleep = _sleep
        assert rec2.on_failed(ASSIGN, attempt=1) == "running"
        assert state2["outbox"] == []
        assert any(s > 0 for s in sleeps)
    finally:
        bw.time.sleep = old_sleep


def test_cursor_giveup_still_fires_when_idle_through_grace():
    sleeps: list[float] = []
    rec, state = _cursor_recovery(
        reinject=lambda line, cb: False,
        acked=True,
        running=False,
    )
    old_sleep = bw.time.sleep
    try:
        bw._submit_verify_giveup_grace_s = lambda default=20.0: 0.15  # type: ignore
        bw.time.sleep = lambda s: sleeps.append(float(s))
        assert rec.on_failed(ASSIGN, attempt=1) == "giveup"
        assert state["outbox"] == [GIVEUP]
        assert sleeps  # grace polled
    finally:
        bw.time.sleep = old_sleep


def test_cursor_inject_stop_fn_uses_turn_not_receipt_ack():
    """Wire helper: Cursor stop predicate is turn_open or probe, not ack_open alone."""
    assert hasattr(bw, "cursor_submit_verify_stop")
    probe_hits = {"n": 0}

    class Bored:
        turn_open = False
        ack_open = True
        ack_job_ref = "SimonBarnett/bobiverse#4505"

    b = Bored()
    stop = bw.cursor_submit_verify_stop(b, probe=lambda: False)
    assert stop() is False  # receipt ACK alone must not stop
    b.turn_open = True
    assert stop() is True
    b.turn_open = False
    stop2 = bw.cursor_submit_verify_stop(b, probe=lambda: True)
    assert stop2() is True
