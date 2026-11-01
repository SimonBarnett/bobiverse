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


def test_fr5687_export_empty_worker_list_clears_jobs_and_running(tmp_path, monkeypatch):
    # FR #5698: portable pytest tmp_path (fixed drive Temp folders are seat-local).
    home = tmp_path / "digest"
    home.mkdir()
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    _roster(home)
    ent = {
        "online": True,
        "running": 1,
        "queued": 0,
        "jobs": [{"repo": "SimonBarnett/hrsmith", "state": "running"}],
        "worker_list": [],
        "working_on": "stale",
        "repo": "SimonBarnett/hrsmith",
        "sha": "deadbeef",
        "started_at": "2026-11-01T11:00:00Z",
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
    assert out.get("repo") in ("", None)
    assert out.get("sha") in ("", None)
    assert out.get("started_at") in ("", None)


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


def test_fr5698_idle_refresh_clears_repo_sha_preserves_when_doing():
    """FR #5698 / #5704 / #5724: clear sticky repo/sha when idle; keep when doing."""
    idle = {
        "repo": "SimonBarnett/hrsmith",
        "sha": "abc123",
        "started_at": "2026-11-01T10:00:00Z",
        "jobs": [{"repo": "SimonBarnett/hrsmith", "state": "running"}],
        "worker_list": [],
        "working_on": "stale",
    }
    bobreport._refresh_machine_activity_from_worker_list(idle)
    assert idle["jobs"] == []
    assert idle["repo"] == ""
    assert idle["sha"] == ""
    assert idle["started_at"] == ""
    assert idle["working_on"] == ""

    active = {
        "repo": "SimonBarnett/a-search",
        "sha": "live01",
        "started_at": "2026-11-01T12:00:00Z",
        "jobs": [{"repo": "SimonBarnett/a-search", "state": "running"}],
        "worker_list": [
            {
                "nick": "marchhare-1",
                "state": "doing",
                "work": "SimonBarnett/a-search FR #1",
                "updated": "2026-11-01T12:00:00Z",
            }
        ],
    }
    bobreport._refresh_machine_activity_from_worker_list(active)
    assert active["repo"] == "SimonBarnett/a-search"
    assert active["sha"] == "live01"
    assert active["started_at"] == "2026-11-01T12:00:00Z"
    assert "a-search" in active["working_on"]


def test_fr5698_tip_test_does_not_hardcode_d_temp():
    from pathlib import Path

    import repo_layout

    src = (
        Path(repo_layout.ROOT)
        / "jeeves"
        / "tests"
        / "test_fr5687_digest_export_clears_running_with_jobs.py"
    ).read_text(encoding="utf-8")
    # Export fixture must use pytest tmp_path, not a fixed drive Temp folder.
    body = src.split("def test_fr5698_tip_test_does_not_hardcode_d_temp")[0]
    assert "tempfile." not in body
    assert "D:" + "\\Temp" not in body
    assert "tmp_path" in body
