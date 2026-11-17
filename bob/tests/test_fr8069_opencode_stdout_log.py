"""FR #8069: per-job OpenCode stdout log is redacted, capped, and named on GIVEUP."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import bob_worker as bw
import opencode_stdout_log as slog


def test_fr8069_log_has_header_and_redacts_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("BOB_OPENCODE_STDOUT_LOG", raising=False)
    when = datetime(2026, 11, 17, 15, 50, tzinfo=timezone.utc)
    path = slog.open_log(
        job_key="MRB SimonBarnett/bobiverse#8050",
        seat="redqueen-11676",
        model="opencode-go/deepseek-v4-pro",
        worktree=str(tmp_path / "mrb-8050"),
        now=when,
    )
    assert path is not None
    assert path.name.startswith("SimonBarnett-bobiverse-MRB-8050-redqueen-11676-")
    token = "ghp_" + ("A" * 20)
    slog.append_text(path, "stdout hello\npassword=" + "EXAMPLE\n" + token + "\nstderr tail\n")
    text = path.read_text(encoding="utf-8")
    assert "seat=redqueen-11676" in text
    assert "model=opencode-go/deepseek-v4-pro" in text
    assert "job=MRB SimonBarnett/bobiverse#8050" in text
    assert "worktree=" in text
    assert "start=2026-11-17T15:50:00Z" in text
    assert "stdout hello" in text
    assert "stderr tail" in text
    assert "EXAMPLE" not in text
    assert token not in text
    assert "<redacted" in text


def test_fr8069_size_cap_and_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    directory = slog.logs_dir()
    directory.mkdir(parents=True)
    path = directory / "repo-MRB-1-seat-a-20260101T000000Z.log"
    path.write_text("seat=seat-a\n", encoding="utf-8")
    slog.append_text(path, "x" * 80, max_bytes=40)
    body = path.read_bytes()
    assert len(body) <= 40
    assert b"[truncated]" in body
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for n in range(55):
        stamp = (base + timedelta(seconds=n)).strftime("%Y%m%dT%H%M%SZ")
        item = directory / ("repo-MRB-1-seat-a-%s.log" % stamp)
        item.write_text("n\n", encoding="utf-8")
        ts = (base + timedelta(seconds=n)).timestamp()
        os_utime = __import__("os").utime
        os_utime(item, (ts, ts))
    slog.prune_seat_logs(directory, "seat-a", keep=50)
    left = [p for p in directory.glob("*.log") if "-seat-a-" in p.name]
    assert len(left) == 50


def test_fr8069_off_switch_and_giveup_names_log(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("BOB_OPENCODE_STDOUT_LOG", "0")
    assert slog.open_log(job_key="FR SimonBarnett/bobiverse#1", seat="s", model="m", worktree="w") is None
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
    assert "BOB_OPENCODE_STDOUT_LOG" in ps1
    assert "RedirectStandardOutput" in ps1
    assert "log=' + [IO.Path]::GetFileName($script:ocStdoutLog)" in ps1
    assert "stdout_log" in ps1
