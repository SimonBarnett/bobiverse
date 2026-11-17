"""FR #8033: prepare failure must not leave OPENCODE_DB empty (shared store)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _launch_ps1(tmp_path: Path) -> str:
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        str(tmp_path / "opencode.exe"),
        tmp_path / "run",
        None,
    )
    return next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))


def test_fr8033_launcher_prepare_failure_sets_opencode_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_SEAT_DATA_ROOT", str(tmp_path / "seats"))
    monkeypatch.setenv("BOB_NICK", "unit-seat")
    ps1 = _launch_ps1(tmp_path)
    assert "opencode-seat-isolate: prepare failed" in ps1
    # FR #8033: after prepare catch / miss, OPENCODE_DB must be forced unique.
    assert "FR #8033" in ps1
    assert "-not $env:OPENCODE_DB" in ps1 or "not $env:OPENCODE_DB" in ps1
    assert "$env:OPENCODE_DB =" in ps1 or '$env:OPENCODE_DB =' in ps1
    # Must create a per-seat path under seat data root / LocalAppData, not rely on shared default.
    assert "opencode-seat-isolate: fallback data dir" in ps1
    # Guard must set all three isolation env vars.
    assert "$env:XDG_DATA_HOME" in ps1
    assert "$env:BOB_OPENCODE_DATA_DIR" in ps1
    assert "opencode.db" in ps1


def test_fr8033_fallback_paths_are_unique_per_seat(tmp_path: Path, monkeypatch):
    import opencode_seat_isolate as iso

    monkeypatch.setenv("BOB_OPENCODE_SEAT_DATA_ROOT", str(tmp_path))
    a = iso.fallback_seat_paths(
        {"BOB_NICK": "a", "BOB_WORKER_PID": "1", "BOB_OPENCODE_SEAT_DATA_ROOT": str(tmp_path)},
        unique="aaa11111",
    )
    b = iso.fallback_seat_paths(
        {"BOB_NICK": "b", "BOB_WORKER_PID": "2", "BOB_OPENCODE_SEAT_DATA_ROOT": str(tmp_path)},
        unique="bbb22222",
    )
    assert a[2].name == "opencode.db"
    assert a[1] != b[1]
    assert "aaa11111" in str(a[0])
    assert a[2].parent == a[1]
