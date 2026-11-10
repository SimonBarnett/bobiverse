"""FR #6420: OpenCode DONE carries model + token counts from its SQLite session data.

The worker reads ``opencode.db`` (read-only) and Jeeves already records the DONE
line's ``model=`` / ``tokens_in=`` / ``tokens_out=`` / ``tokens_cached=`` into the
per-PR cost ledger. These tests cover the OpenCode reader and the ledger round-trip:
a DONE with real session stats populates the row; missing stats leave fields blank
(``tokens_unknown``) and are never invented.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import done_usage
import job_cost_ledger
import shop_listen


def _write_opencode_db(data_dir: Path, sessions: list[dict]) -> Path:
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
    for s in sessions:
        con.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                s["id"],
                "proj",
                s.get("parent_id"),
                s["directory"],
                "title",
                0.0,
                s.get("model"),
                s.get("tokens_input", 0),
                s.get("tokens_output", 0),
                s.get("tokens_reasoning", 0),
                s.get("tokens_cache_read", 0),
                s.get("tokens_cache_write", 0),
            ),
        )
    con.commit()
    con.close()
    return db


_MODEL = json.dumps({"id": "deepseek-v4-pro", "providerID": "opencode-go"})


def test_read_opencode_sqlite_usage_sums_matching_sessions(tmp_path: Path):
    wt = tmp_path / "worktrees" / "bobiverse" / "fr-6420"
    wt.mkdir(parents=True)
    data_dir = tmp_path / "opencode"
    _write_opencode_db(
        data_dir,
        [
            {"id": "s1", "directory": str(wt), "model": _MODEL,
             "tokens_input": 100, "tokens_output": 20, "tokens_cache_read": 50},
            {"id": "s2", "directory": str(wt), "model": _MODEL,
             "tokens_input": 5, "tokens_output": 2, "tokens_cache_read": 3},
            {"id": "s3", "directory": str(tmp_path / "other"), "model": _MODEL,
             "tokens_input": 999, "tokens_output": 999, "tokens_cache_read": 999},
        ],
    )
    u = done_usage.read_opencode_sqlite_usage(data_dir, directory=str(wt))
    assert u["model"] == "opencode-go/deepseek-v4-pro"
    assert u["tokens_in"] == 105
    assert u["tokens_out"] == 22
    assert u["tokens_cached"] == 53
    assert u["tokens_unknown"] is False


def test_read_opencode_sqlite_usage_missing_db_is_unknown(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    u = done_usage.read_opencode_sqlite_usage(tmp_path / "nodb", directory=str(wt))
    assert u["tokens_unknown"] is True
    assert u["tokens_in"] is None
    assert u["tokens_out"] is None
    assert u["tokens_cached"] is None
    assert u["model"] == ""


def test_read_opencode_sqlite_usage_no_matching_directory_is_unknown(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    data_dir = tmp_path / "opencode"
    _write_opencode_db(
        data_dir,
        [{"id": "s1", "directory": str(tmp_path / "elsewhere"), "model": _MODEL,
          "tokens_input": 1, "tokens_output": 1, "tokens_cache_read": 1}],
    )
    u = done_usage.read_opencode_sqlite_usage(data_dir, directory=str(wt))
    assert u["tokens_unknown"] is True
    assert u["model"] == ""


def test_read_opencode_sqlite_usage_empty_directory_is_unknown(tmp_path: Path):
    data_dir = tmp_path / "opencode"
    _write_opencode_db(
        data_dir,
        [{"id": "s1", "directory": str(tmp_path), "model": _MODEL,
          "tokens_input": 1, "tokens_output": 1, "tokens_cache_read": 1}],
    )
    u = done_usage.read_opencode_sqlite_usage(data_dir, directory="")
    assert u["tokens_unknown"] is True


def test_cache_dict_shape_reads_as_cached(tmp_path: Path):
    doc = {
        "model": "opencode/glm-5.3",
        "tokens": {
            "input": 200,
            "output": 15,
            "reasoning": 0,
            "cache": {"read": 40, "write": 12},
        },
    }
    path = tmp_path / "opencode-session.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    u = done_usage.read_opencode_usage(path)
    assert u["model"] == "opencode/glm-5.3"
    assert u["tokens_in"] == 200
    assert u["tokens_out"] == 15
    assert u["tokens_cached"] == 40


def test_opencode_done_with_session_stats_populates_ledger(tmp_path: Path):
    wt = tmp_path / "worktrees" / "bobiverse" / "fr-6420"
    wt.mkdir(parents=True)
    data_dir = tmp_path / "opencode"
    _write_opencode_db(
        data_dir,
        [{"id": "s1", "directory": str(wt), "model": _MODEL,
          "tokens_input": 100, "tokens_output": 20, "tokens_cache_read": 50}],
    )
    home = tmp_path / "home"
    home.mkdir()
    usage = done_usage.read_opencode_sqlite_usage(data_dir, directory=str(wt))
    done_line = done_usage.enrich_done_payload(
        "DONE FR o/r#6420 https://github.com/o/r/pull/6420",
        usage,
        worker_build="deadbeefcafe",
    )
    parsed = shop_listen.parse_shop_job_line(done_line)
    assert parsed is not None
    row = job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#6420",
        task="FR",
        seat="marchhare-1",
        rest=parsed.rest,
        url=parsed.url,
    )
    assert row["model"] == "opencode-go/deepseek-v4-pro"
    assert row["tokens_in"] == 100
    assert row["tokens_out"] == 20
    assert row["tokens_cached"] == 50
    assert row["tokens_unknown"] is False


def test_opencode_done_missing_stats_ledger_stays_blank(tmp_path: Path):
    wt = tmp_path / "wt"
    wt.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    usage = done_usage.read_opencode_sqlite_usage(tmp_path / "nodb", directory=str(wt))
    done_line = done_usage.enrich_done_payload(
        "DONE FR o/r#6420 https://github.com/o/r/pull/6420",
        usage,
        worker_build="deadbeefcafe",
    )
    assert "tokens=unknown" in done_line
    assert "tokens_in=" not in done_line
    parsed = shop_listen.parse_shop_job_line(done_line)
    assert parsed is not None
    row = job_cost_ledger.record_done(
        home,
        repo="o/r",
        ident="#6420",
        task="FR",
        seat="marchhare-1",
        rest=parsed.rest,
        url=parsed.url,
    )
    assert row["model"] == ""
    assert row["tokens_in"] is None
    assert row["tokens_out"] is None
    assert row["tokens_cached"] is None
    assert row["tokens_unknown"] is True
