"""MRB #7894: in-window local stall still files when the pool age is past six hours."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bobreport


def test_remote_inside_window_does_not_file(monkeypatch):
    filed: list[str] = []

    def _capture(component, message, *, site=""):
        filed.append(message)
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report_message", _capture)
    monkeypatch.setenv("BOB_MACHINE_ID", "walrus")
    bobreport.report_stale_ear_publish("marchhare", 150, why="lastSeen")
    assert filed == []


def test_in_window_last_seen_reports_when_pool_is_past_window():
    now = datetime(2026, 11, 16, 9, 35, tzinfo=timezone.utc)
    seen = (now - timedelta(seconds=150)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pool = (now - timedelta(seconds=29917)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filed: list[tuple] = []

    def _report(mid, age_s, *, why):
        filed.append((mid, int(age_s), why))

    orig = bobreport.report_stale_ear_publish
    bobreport.report_stale_ear_publish = _report
    try:
        ent = {
            "id": "walrus",
            "online": True,
            "lastSeen": seen,
            "xai_weekly": {"remaining_pct": 10, "fresh": True, "fetched_at": pool},
        }
        assert bobreport.apply_ear_publish_staleness(ent, now, machine_id="walrus", report=True)
    finally:
        bobreport.report_stale_ear_publish = orig
    assert ent["online"] is False
    assert ent["xai_weekly"]["fresh"] is False
    assert filed == [("walrus", 150, "lastSeen")]
