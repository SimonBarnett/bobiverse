# -*- coding: utf-8 -*-
"""FR #8514: after digest-fuel-stall, abandon the hung worker and start a new publish."""
from __future__ import annotations

import threading

import bobreport
import irc_agent


def test_fr8514_stalled_fuel_publish_is_abandoned_and_restarted():
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    reports: list[str] = []

    class Ear(irc_agent.Client):
        def __init__(self):
            self.original_nick = "bob-redqueen"
            self.home = "."
            self._digest_fuel_last = 0.0
            self._fuel_worker = None
            self._fuel_worker_started = 0.0
            self._fuel_stall_reported = False
            self.args = type("A", (), {"chair": False})()

        def _local_machine_id(self):
            return "redqueen"

    ear = Ear()

    def _hang(home, mid, **kw):
        calls["n"] += 1
        started.set()
        # First call hangs; later calls return quickly so the restart is observable.
        if calls["n"] == 1:
            release.wait(30)
        return 204

    import runtime_failure

    real_publish = bobreport.publish_local_peer_fuel
    real_due = bobreport.digest_fuel_delta_s
    real_report = runtime_failure.report_message

    def _capture(component, message, *, site=""):
        reports.append(site)
        return {"ok": True}

    bobreport.publish_local_peer_fuel = _hang
    bobreport.digest_fuel_delta_s = lambda: 0.0
    runtime_failure.report_message = _capture
    hung = None
    try:
        ear._fuel_worker_started = 0.0
        ear._maybe_publish_digest_fuel()
        assert started.wait(2)
        hung = ear._fuel_worker
        assert hung is not None and hung.is_alive()
        assert calls["n"] == 1

        ear._digest_fuel_last = 0.0
        ear._fuel_worker_started = ear._fuel_worker_started - 130
        ear._maybe_publish_digest_fuel()

        assert "digest-fuel-stall" in reports
        assert calls["n"] == 2
        assert ear._fuel_worker is not None
        assert ear._fuel_worker is not hung
        assert hung.is_alive()  # orphan still blocked until release
    finally:
        release.set()
        bobreport.publish_local_peer_fuel = real_publish
        bobreport.digest_fuel_delta_s = real_due
        runtime_failure.report_message = real_report
        if hung is not None:
            hung.join(2)
        if ear._fuel_worker is not None:
            ear._fuel_worker.join(2)


def test_fr8514_in_flight_under_stale_window_still_waits():
    release = threading.Event()
    calls = {"n": 0}

    class Ear(irc_agent.Client):
        def __init__(self):
            self.original_nick = "bob-redqueen"
            self.home = "."
            self._digest_fuel_last = 0.0
            self._fuel_worker = None
            self._fuel_worker_started = 0.0
            self._fuel_stall_reported = False
            self.args = type("A", (), {"chair": False})()

        def _local_machine_id(self):
            return "redqueen"

    ear = Ear()

    def _hang(home, mid, **kw):
        calls["n"] += 1
        release.wait(30)
        return 204

    real_publish = bobreport.publish_local_peer_fuel
    real_due = bobreport.digest_fuel_delta_s
    bobreport.publish_local_peer_fuel = _hang
    bobreport.digest_fuel_delta_s = lambda: 0.0
    try:
        ear._maybe_publish_digest_fuel()
        first = ear._fuel_worker
        assert first is not None and first.is_alive()
        ear._digest_fuel_last = 0.0
        # Age under EAR_PUBLISH_STALE_S (120s): must not abandon.
        ear._fuel_worker_started = ear._fuel_worker_started - 30
        ear._maybe_publish_digest_fuel()
        assert calls["n"] == 1
        assert ear._fuel_worker is first
    finally:
        release.set()
        bobreport.publish_local_peer_fuel = real_publish
        bobreport.digest_fuel_delta_s = real_due
        if ear._fuel_worker is not None:
            ear._fuel_worker.join(2)
