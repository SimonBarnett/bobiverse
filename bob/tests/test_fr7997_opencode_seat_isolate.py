"""FR #7997: per-seat OpenCode data dir, lock retry, startup giveup."""
from __future__ import annotations

import os
from pathlib import Path

import bob_worker as bw
import opencode_seat_isolate as iso


def test_fr7997_two_seats_get_different_data_dirs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_SEAT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    a = iso.seat_paths({"BOB_NICK": "red-1", "BOB_WORKER_PID": "11", "BOB_OPENCODE_SEAT_DATA_ROOT": str(tmp_path)})
    b = iso.seat_paths({"BOB_NICK": "red-2", "BOB_WORKER_PID": "22", "BOB_OPENCODE_SEAT_DATA_ROOT": str(tmp_path)})
    assert a[1] != b[1]
    assert a[2].name == "opencode.db"
    assert b[2].parent == b[1]


def test_fr7997_prepare_copies_auth_not_db(tmp_path: Path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "auth.json").write_text('{"FAKE_AUTH":"example"}', encoding="utf-8")
    (shared / "opencode.db").write_bytes(b"not-a-real-db")
    env = {
        "BOB_NICK": "seat-a",
        "BOB_WORKER_PID": "9",
        "BOB_OPENCODE_SEAT_DATA_ROOT": str(tmp_path / "seats"),
        "USERPROFILE": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(shared.parent),
    }
    # shared auth lives at <xdg>/opencode/auth.json — place it there.
    data_shared = shared.parent / "opencode"
    data_shared.mkdir(parents=True, exist_ok=True)
    (data_shared / "auth.json").write_text('{"FAKE_AUTH":"example"}', encoding="utf-8")
    (data_shared / "opencode.db").write_bytes(b"shared-db")
    root, data, db = iso.prepare_seat_data(env)
    assert (data / "auth.json").is_file()
    assert not db.is_file()
    assert "shared-db" not in (data / "auth.json").read_text(encoding="utf-8")
    assert root != data


def test_fr7997_classify_lock_retries_then_giveup():
    assert iso.classify_startup("Error: database is locked", exit_code=1, attempt=0, max_retries=3) == "retry"
    assert iso.classify_startup("SQLITE_BUSY", exit_code=1, attempt=2, max_retries=3) == "retry"
    assert iso.classify_startup("database is locked", exit_code=1, attempt=3, max_retries=3) == "giveup"
    assert iso.classify_startup("Error: Unexpected error", exit_code=1, attempt=0) == "giveup"
    assert iso.classify_startup("rate limit", exit_code=1, attempt=0) == "continue"
    assert iso.classify_startup("database is locked", exit_code=0, attempt=0) == "continue"
    assert iso.classify_startup("task failed", exit_code=1, attempt=0) == "continue"
    banner = "\x1b[2J\x1b]0;opencode.exe\x07> build \u00b7 claude-haiku-5-5"
    assert iso.handshake_only(banner)
    assert iso.classify_startup(banner, exit_code=-1, attempt=0) == "retry"
    assert iso.classify_startup(banner, exit_code=-1, attempt=1) == "giveup"
    assert iso.classify_startup("skill-dag_list_catalog Unknown", exit_code=-1, attempt=0) == "continue"
    assert iso.classify_startup("", exit_code=1, attempt=0) == "retry"
    leftover = "[?9001h[?1004h> build claude-haiku-5-5"
    assert iso.handshake_only(leftover)
    assert iso.classify_startup(leftover, exit_code=-1, attempt=0) == "retry"


def test_fr7997_launcher_isolates_and_retries(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BOB_OPENCODE_SEAT_DATA_ROOT", str(tmp_path / "seats"))
    monkeypatch.setenv("BOB_NICK", "unit-seat")
    spec = bw.build_launch(
        "opencode",
        "agent",
        str(tmp_path / "cwd"),
        "hello",
        str(tmp_path / "opencode.exe"),
        tmp_path / "run",
        None,
    )
    ps1 = next(v for k, v in spec.files.items() if str(k).endswith("launch-opencode.ps1"))
    assert "opencode_seat_isolate.py" in ps1
    assert "XDG_DATA_HOME" in ps1
    assert "OPENCODE_DB" in ps1
    assert "classify" in ps1
    assert "opencode-startup-failed" in ps1
    assert "ConvertTo-OpencodePlain" in ps1
    assert "opencode-startup-failed exit=" in ps1
    assert "pythonw.exe" in ps1
    assert "opencode-handshake: retry" in ps1
    assert "else { '' }" not in ps1
    assert "'--cwd', $ocDir" in ps1
    assert "opencode-data-dir.txt" in ps1
    assert "FR #7997" in ps1
