"""FR #7892: a long-offline remote machine is not a bob-ear crash."""
from __future__ import annotations

import bobreport


def test_remote_or_long_offline_does_not_file(monkeypatch):
    filed: list[str] = []

    def _capture(component, message, *, site=""):
        filed.append(f"{component}|{site}|{message}")
        return {"ok": True}

    import runtime_failure

    monkeypatch.setattr(runtime_failure, "report_message", _capture)
    monkeypatch.setenv("BOB_MACHINE_ID", "walrus")
    bobreport.report_stale_ear_publish("marchhare", 29917, why="lastSeen+fetched_at")
    bobreport.report_stale_ear_publish("walrus", 29917, why="lastSeen")
    assert filed == []
    bobreport.report_stale_ear_publish("walrus", 150, why="lastSeen")
    assert len(filed) == 1
    assert "age_s=" not in filed[0]
    assert "machine=walrus" in filed[0]
    assert "RuntimeError" not in filed[0]
