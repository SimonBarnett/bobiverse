"""FR #7499: digest running/jobs reflect worker_list seats in state doing."""
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


def test_fr7499_one_doing_worker_sets_running_and_job():
    ent = {
        "running": 0,
        "queued": 0,
        "jobs": [],
        "worker_list": [
            {
                "nick": "marchhare-1",
                "state": "doing",
                "work": "bobiverse FR #7465",
                "updated": "2026-11-15T14:31:00Z",
            }
        ],
    }
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert ent["running"] == 1
    assert len(ent["jobs"]) == 1
    job = ent["jobs"][0]
    assert job.get("nick") == "marchhare-1"
    assert job.get("repo") == "bobiverse"
    assert job.get("issue") == "7465"
    assert job.get("updated") == "2026-11-15T14:31:00Z"
    assert "7465" in (ent.get("working_on") or "")


def test_fr7499_all_idle_clears_running_and_jobs():
    ent = {
        "running": 2,
        "queued": 1,
        "jobs": [{"repo": "SimonBarnett/bobiverse", "state": "running", "issue": "1"}],
        "worker_list": [
            {
                "nick": "marchhare-1",
                "state": "idle",
                "work": "",
                "updated": "2026-11-15T14:40:00Z",
            }
        ],
        "working_on": "stale",
        "repo": "SimonBarnett/bobiverse",
        "sha": "dead",
        "started_at": "2026-11-15T14:00:00Z",
    }
    bobreport._refresh_machine_activity_from_worker_list(ent)
    assert ent["running"] == 0
    assert ent["jobs"] == []
    assert ent.get("working_on") == ""


def test_fr7499_export_doing_worker_publishes_running_job(tmp_path, monkeypatch):
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    ent = {
        "online": True,
        "running": 0,
        "jobs": [],
        "worker_list": [
            {
                "nick": "marchhare-42",
                "state": "doing",
                "work": "SimonBarnett/bobiverse FR #7465",
                "updated": "2026-11-15T14:31:00Z",
            }
        ],
    }
    out = bobreport.export_machine_for_tray(
        home,
        "marchhare",
        ent,
        now=datetime(2026, 11, 15, 14, 32, tzinfo=timezone.utc),
    )
    assert out.get("running") == 1
    jobs = out.get("jobs") or []
    assert len(jobs) == 1
    assert jobs[0].get("nick") == "marchhare-42"
    assert jobs[0].get("issue") == "7465"
    assert "bobiverse" in (jobs[0].get("repo") or "")
