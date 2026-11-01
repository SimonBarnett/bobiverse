"""FR #5687: export clearing jobs must also zero running/queued.

MarchHare digest showed running=1 with jobs=[] after
_refresh_machine_activity_from_worker_list dropped jobs when no worker_list
row was doing, leaving peer running/queued untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import bobreport


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def test_fr5687_export_empty_worker_list_clears_jobs_and_running(monkeypatch):
    # Prefer an explicit D: home: pytest's default tmp_path can hit WinError 5
    # under D:\Temp\pytest-of-* on this seat.
    import tempfile

    home = Path(tempfile.mkdtemp(prefix="fr5687-", dir="D:\\Temp"))
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    ent = {
        "online": True,
        "running": 1,
        "queued": 0,
        "jobs": [{"repo": "SimonBarnett/hrsmith", "state": "running"}],
        "worker_list": [],
        "working_on": "stale",
    }
    out = bobreport.export_machine_for_tray(
        home,
        "marchhare",
        ent,
        now=datetime(2026, 11, 1, 12, tzinfo=timezone.utc),
    )
    assert out.get("jobs") == []
    assert out.get("running") == 0
    assert out.get("queued") == 0
    assert out.get("working_on") == ""


def test_fr5687_refresh_syncs_running_queued_from_jobs():
    ent = {
        "running": 9,
        "queued": 9,
        "jobs": [
            {"repo": "SimonBarnett/a", "state": "running"},
            {"repo": "SimonBarnett/b", "state": "queued"},
        ],
        "worker_list": [
            {
                "nick": "marchhare-1",
                "state": "doing",
                "work": "SimonBarnett/a FR #1",
                "updated": "2026-11-01T12:00:00Z",
            }
        ],
    }
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert len(ent.get("jobs") or []) == 2
    assert ent["running"] == 1
    assert ent["queued"] == 1


def test_fr5687_sync_helper_empty_jobs_zeros_counts():
    ent = {"running": 3, "queued": 2, "jobs": []}
    bobreport._sync_running_queued_from_jobs(ent)
    assert ent["running"] == 0
    assert ent["queued"] == 0
