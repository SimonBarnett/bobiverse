# -*- coding: utf-8 -*-
"""FR #7839: a stalled ear publish is stale within 2 min and is reported."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import bobreport
import irc_agent


def test_fr7839_stale_last_seen_marks_offline_and_reports():
    now = datetime(2026, 11, 16, 2, 9, tzinfo=timezone.utc)
    seen = (now - timedelta(seconds=150)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filed: list[str] = []

    def _report(mid, age_s, *, why):
        filed.append(f"{mid}:{why}:{int(age_s)}")

    orig = bobreport.report_stale_ear_publish
    bobreport.report_stale_ear_publish = _report
    try:
        ent = {
            "id": "marchhare",
            "online": True,
            "status": "I am online",
            "lastSeen": seen,
            "xai_weekly": {
                "remaining_pct": 24,
                "fresh": True,
                "fetched_at": seen,
                "period_end": "2026-11-22T19:28:00Z",
            },
        }
        assert bobreport.apply_ear_publish_staleness(
            ent, now, machine_id="marchhare", report=True
        )
    finally:
        bobreport.report_stale_ear_publish = orig
    assert ent["online"] is False
    assert ent["xai_weekly"]["fresh"] is False
    assert ent["xai_weekly"]["remaining_pct"] == 24
    assert ent["xai_weekly"]["period_end"] == "2026-11-22T19:28:00Z"
    assert filed and filed[0].startswith("marchhare:")
    assert int(filed[0].rsplit(":", 1)[-1]) >= 120


def test_fr7839_fresh_row_is_not_marked():
    now = datetime(2026, 11, 16, 2, 9, tzinfo=timezone.utc)
    seen = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    ent = {
        "online": True,
        "lastSeen": seen,
        "xai_weekly": {"remaining_pct": 24, "fresh": True, "fetched_at": seen},
    }
    assert bobreport.apply_ear_publish_staleness(ent, now, report=False) is False
    assert ent["online"] is True
    assert ent["xai_weekly"]["fresh"] is True


def test_fr7839_hung_fuel_publish_does_not_stop_the_loop():
    started = threading.Event()
    release = threading.Event()
    reports: list[str] = []

    class Ear(irc_agent.Client):
        def __init__(self):
            self.original_nick = "bob-marchhare"
            self.home = "."
            self._digest_fuel_last = 0.0
            self._fuel_worker = None
            self._fuel_worker_started = 0.0
            self._fuel_stall_reported = False
            self.args = type("A", (), {"chair": False})()

        def _local_machine_id(self):
            return "marchhare"

    ear = Ear()
    real_publish = bobreport.publish_local_peer_fuel
    real_due = bobreport.digest_fuel_delta_s
    real_report = None

    def _hang(home, mid, **kw):
        started.set()
        release.wait(30)
        return 204

    import runtime_failure

    real_report = runtime_failure.report_message

    def _capture(component, message, *, site=""):
        reports.append(site)
        return {"ok": True}

    bobreport.publish_local_peer_fuel = _hang
    bobreport.digest_fuel_delta_s = lambda: 0.0
    runtime_failure.report_message = _capture
    try:
        ear._fuel_worker_started = 0.0
        ear._maybe_publish_digest_fuel()
        assert started.wait(2)
        assert ear._fuel_worker is not None and ear._fuel_worker.is_alive()
        # Loop would tick again while the publish is still hung.
        hung = ear._fuel_worker
        ear._digest_fuel_last = 0.0
        ear._fuel_worker_started = ear._fuel_worker_started - 130
        ear._maybe_publish_digest_fuel()
        assert "digest-fuel-stall" in reports
        # FR #8514: stalled worker is abandoned; a new publish thread is started.
        assert ear._fuel_worker is not None and ear._fuel_worker.is_alive()
        assert ear._fuel_worker is not hung
        assert hung.is_alive()
    finally:
        release.set()
        bobreport.publish_local_peer_fuel = real_publish
        bobreport.digest_fuel_delta_s = real_due
        runtime_failure.report_message = real_report
        if ear._fuel_worker is not None:
            ear._fuel_worker.join(2)
