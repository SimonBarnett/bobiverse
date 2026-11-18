"""FR #8147: classify must never crash on an empty/unknown exit code, and a
finished (DONE/GIVEUP) job is never re-classified as a startup failure."""
from __future__ import annotations

import io
from pathlib import Path

import bob_worker as bw
import opencode_seat_isolate as iso


def test_fr8147_classify_unknown_exit_code_is_not_a_crash():
    # Empty/null exit code (wrapper echoed `exit=` after a cmdlet-only step).
    assert iso.classify_startup("", exit_code=None, attempt=0) == "continue"
    assert iso.classify_startup("task failed", exit_code=None, attempt=0) == "continue"
    assert iso.classify_startup("task failed", exit_code="", attempt=0) == "continue"


def test_fr8147_classify_unknown_exit_code_still_sees_lock_cues():
    assert iso.classify_startup("database is locked", exit_code=None, attempt=0, max_retries=3) == "retry"
    assert iso.classify_startup("unexpected error", exit_code=None, attempt=0) == "giveup"


def test_fr8147_classify_done_overrides_failure_cues():
    # A job whose outbox already has DONE/GIVEUP must not be a startup failure.
    assert iso.classify_startup("unexpected error", exit_code=1, attempt=0, done=True) == "continue"
    assert iso.classify_startup("database is locked", exit_code=1, attempt=3, max_retries=3, done=True) == "continue"
    assert iso.classify_startup("", exit_code=None, attempt=0, done=True) == "continue"


def test_fr8147_classify_cmd_accepts_empty_and_missing_exit(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert iso.main(["classify", "--attempt", "0", "--max", "3", "--exit"]) == 0
    assert capsys.readouterr().out.strip() == "continue"


def test_fr8147_classify_cmd_accepts_empty_string_exit(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert iso.main(["classify", "--attempt", "0", "--max", "3", "--exit", ""]) == 0
    assert capsys.readouterr().out.strip() == "continue"


def test_fr8147_classify_cmd_explicit_exit_still_works(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("database is locked"))
    assert iso.main(["classify", "--attempt", "0", "--max", "3", "--exit", "1"]) == 0
    assert capsys.readouterr().out.strip() == "retry"


def test_fr8147_launcher_guards_exit_and_handles_null_classify(tmp_path: Path):
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
    assert "classify" in ps1
    # Never pass a null/empty exit code: guard on $exitCode, omit --exit when unknown.
    assert "$clsExit" in ps1
    assert "classify_unavailable" in ps1
    assert "--done" in ps1
    assert "DONE|GIVEUP|NACK" in ps1
