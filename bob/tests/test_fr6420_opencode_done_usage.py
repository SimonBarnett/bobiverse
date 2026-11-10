"""FR #6420: worker measures OpenCode DONE usage from its SQLite session data."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import done_usage  # noqa: E402


def _write_opencode_db(data_dir: Path, directory: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "opencode.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE session ("
        "id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT, directory TEXT, "
        "title TEXT, cost REAL, model TEXT, tokens_input INTEGER, "
        "tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, "
        "tokens_cache_write INTEGER)"
    )
    con.execute(
        "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "s1",
            "proj",
            None,
            directory,
            "title",
            0.0,
            json.dumps({"id": "deepseek-v4-pro", "providerID": "opencode-go"}),
            100,
            20,
            0,
            50,
            0,
        ),
    )
    con.commit()
    con.close()


def _bound(fake, name: str):
    fn = getattr(bw.Supervisor, name)
    return fn.__get__(fake, type(fake))


def _make_fake(tmp_path: Path, worktree: Path):
    fake = type("_Fake", (), {})()
    fake.kind = "opencode"
    fake.run_dir = tmp_path
    fake._opencode_job_outbox = Path(worktree) / ".bob" / "outbox.txt"
    for name in ("measure_done_usage", "_measure_opencode_usage", "_opencode_job_directory"):
        setattr(fake, name, _bound(fake, name))
    return fake


def test_opencode_job_directory_from_outbox(tmp_path: Path):
    wt = tmp_path / "worktrees" / "bobiverse" / "fr-6420"
    wt.mkdir(parents=True)
    fake = _make_fake(tmp_path, wt)
    assert fake._opencode_job_directory() == str(wt)


def test_opencode_job_directory_empty_without_outbox(tmp_path: Path):
    fake = _make_fake(tmp_path, tmp_path)
    fake._opencode_job_outbox = None
    assert fake._opencode_job_directory() == ""


def test_measure_done_usage_opencode_reads_sqlite(tmp_path: Path, monkeypatch):
    wt = tmp_path / "worktrees" / "bobiverse" / "fr-6420"
    wt.mkdir(parents=True)
    data_dir = tmp_path / "opencode"
    _write_opencode_db(data_dir, str(wt))
    monkeypatch.setenv("BOB_OPENCODE_DATA_DIR", str(data_dir))
    monkeypatch.delenv("BOB_OPENCODE_USAGE_PATH", raising=False)
    monkeypatch.delenv("BOB_OPENCODE_MODEL", raising=False)
    fake = _make_fake(tmp_path, wt)
    usage = fake.measure_done_usage()
    assert usage["model"] == "opencode-go/deepseek-v4-pro"
    assert usage["tokens_in"] == 100
    assert usage["tokens_out"] == 20
    assert usage["tokens_cached"] == 50
    assert usage["tokens_unknown"] is False


def test_measure_done_usage_opencode_falls_back_to_configured_model(
    tmp_path: Path, monkeypatch
):
    wt = tmp_path / "worktrees" / "bobiverse" / "fr-6420"
    wt.mkdir(parents=True)
    monkeypatch.setenv("BOB_OPENCODE_DATA_DIR", str(tmp_path / "nodb"))
    monkeypatch.delenv("BOB_OPENCODE_USAGE_PATH", raising=False)
    monkeypatch.setenv("BOB_OPENCODE_MODEL", "opencode-go/deepseek-v4-pro")
    fake = _make_fake(tmp_path, wt)
    usage = fake.measure_done_usage()
    assert usage["model"] == "opencode-go/deepseek-v4-pro"
    assert usage["tokens_unknown"] is True
    assert usage["tokens_in"] is None
