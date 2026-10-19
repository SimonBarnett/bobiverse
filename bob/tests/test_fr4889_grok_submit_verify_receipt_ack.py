"""FR #4889: grok submit-verify must not stop on relay ACK-on-receipt.

ACK on receipt (FR #4115) sets ack_open for the same job before inject. The
grok path used that as stop evidence and logged ok (stop/ACK) without Enter
retries, so an unsubmitted paste sat until ack-stale. Same class as Cursor
FR #4732 (turn_open|probe only).
"""
from __future__ import annotations

import bob_worker as bw


ASSIGN = (
    "FROM Jeeves #ionos win-mpre8vi4u6u-8944: MRB SimonBarnett/bobiverse#4859 "
    "https://github.com/SimonBarnett/bobiverse/pull/4859"
)


class _Bored:
    def __init__(self):
        self.ack_open = True
        self.ack_job_ref = "simonbarnett/bobiverse#4859"
        self.turn_open = False


def test_grok_receipt_ack_retries_until_probe_then_ok():
    """Acceptance: receipt ACK + probe false for two Enters, true after third."""
    clock = {"t": 0.0}
    state = {"enters": 0, "probe_after": 3, "injects": 0}
    logs: list[str] = []
    bored = _Bored()

    def inject(pid, text, submit_gap_s=None):
        state["injects"] += 1
        return True

    def enter(*a, **k):
        state["enters"] += 1
        return True

    def probe():
        return state["enters"] >= state["probe_after"]

    def sleep(dt):
        clock["t"] += float(dt)

    stop = bw.cursor_submit_verify_stop(bored, probe=probe)
    res = bw.run_submit_verify_loop(
        enter_fn=enter,
        probe_fn=probe,
        clock=lambda: clock["t"],
        sleep=sleep,
        log=logs.append,
        verify_s=0.05,
        max_retries=3,
        backoffs=(0.05, 0.05, 0.05),
        stop_fn=stop,
        t0=0.0,
    )
    assert res == "ok"
    assert state["enters"] >= 1
    assert any("submit-verify retry=" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)
    assert any("(probe)" in m for m in logs)


def test_grok_probe_immediate_ok_no_retry():
    clock = {"t": 0.0}
    logs: list[str] = []
    enters = {"n": 0}
    bored = _Bored()

    def enter(*a, **k):
        enters["n"] += 1
        return True

    stop = bw.cursor_submit_verify_stop(bored, probe=lambda: True)
    res = bw.run_submit_verify_loop(
        enter_fn=enter,
        probe_fn=lambda: True,
        clock=lambda: clock["t"],
        sleep=lambda dt: clock.__setitem__("t", clock["t"] + float(dt)),
        log=logs.append,
        verify_s=0.05,
        max_retries=3,
        backoffs=(0.05, 0.05, 0.05),
        stop_fn=stop,
        t0=0.0,
    )
    assert res == "ok"
    assert enters["n"] == 0
    assert not any("submit-verify retry=" in m for m in logs)
    assert any("(probe)" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)


def test_grok_probe_never_fails_no_stop():
    clock = {"t": 0.0}
    logs: list[str] = []
    enters = {"n": 0}
    bored = _Bored()

    def enter(*a, **k):
        enters["n"] += 1
        return True

    stop = bw.cursor_submit_verify_stop(bored, probe=lambda: False)
    res = bw.run_submit_verify_loop(
        enter_fn=enter,
        probe_fn=lambda: False,
        clock=lambda: clock["t"],
        sleep=lambda dt: clock.__setitem__("t", clock["t"] + float(dt)),
        log=logs.append,
        verify_s=0.05,
        max_retries=2,
        backoffs=(0.05, 0.05),
        stop_fn=stop,
        t0=0.0,
    )
    assert res == "failed"
    assert enters["n"] >= 1
    assert any("submit-verify FAILED" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)


def test_inject_with_verify_receipt_ack_one_inject():
    """Full inject_with_submit_verify: receipt ACK must not skip retries; one paste."""
    clock = {"t": 0.0}
    logs: list[str] = []
    state = {"enters": 0, "injects": 0}
    bored = _Bored()

    def inject(pid, text, submit_gap_s=None):
        state["injects"] += 1
        return True

    def enter(*a, **k):
        state["enters"] += 1
        return True

    def probe():
        return state["enters"] >= 2

    stop = bw.cursor_submit_verify_stop(bored, probe=probe)
    ok = bw.inject_with_submit_verify(
        1,
        ASSIGN,
        inject_fn=inject,
        enter_fn=enter,
        probe_fn=probe,
        clock=lambda: clock["t"],
        sleep=lambda dt: clock.__setitem__("t", clock["t"] + float(dt)),
        log=logs.append,
        verify_s=0.05,
        max_retries=3,
        backoffs=(0.05, 0.05, 0.05),
        stop_fn=stop,
        sync=True,
    )
    assert ok is True
    assert state["injects"] == 1
    assert any("submit-verify retry=" in m for m in logs)
    assert not any("(stop/ACK)" in m for m in logs)


def test_inject_line_wires_grok_like_cursor_when_probe_present():
    src = open(bw.__file__, encoding="utf-8").read()
    i = src.index("def _inject_line")
    body = src[i : i + 2200]
    assert "FR #4889" in body or "4889" in body
    assert "cursor_submit_verify_stop" in body
    # Must not wire bare ack_open stop when probe is present (receipt-ACK class).
    assert "if probe is not None:" in body or "probe is not None" in body
