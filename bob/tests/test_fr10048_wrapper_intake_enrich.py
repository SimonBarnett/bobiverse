# -*- coding: utf-8 -*-
"""FR #10048 (depends on #10019): wrapper failures intake with seat evidence.

A Clear failure filed through runtime_failure must carry nick / kind / job /
exception class in the intake body, dedupe a repeat inside the rate window, and
the filing path must never shell out to ``gh issue create``.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import bob_worker as bw
import crash_report
import runtime_failure

_CLEAR_PS1 = """\
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [int]$MaxExtraJobTrees = 0,
    [switch]$SkipSeatDisk
)
"""

_SCRIPTS = Path(bw.__file__).resolve().parent
_COMMON = _SCRIPTS.parent.parent / "common" / "scripts"


class _R:
    def __init__(self, code=0, out=""):
        self.returncode = code
        self.stdout = out
        self.stderr = ""


def _setup(tmp_path: Path, monkeypatch) -> Path:
    job = tmp_path / "job"
    job.mkdir()
    (job / ".git").mkdir()
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "install"))
    clear = tmp_path / "install" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
    clear.parent.mkdir(parents=True)
    clear.write_text(_CLEAR_PS1, encoding="utf-8")
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(clear.parent))
    monkeypatch.setenv("BOB_NICK", "bob-seat-test")
    monkeypatch.setenv("BOB_RUNTIME_FAILURE_UNDER_PYTEST", "1")
    monkeypatch.setenv("BOB_RUNTIME_FAILURE_DIR", str(tmp_path / "rf"))
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setenv("BOB_CRASH_REPORT", "full")
    bw._FLEET_PS1_MISMATCH_WARNED.clear()
    runtime_failure._SEEN.clear()
    return job


def _timeout_run(job: Path):
    def run(argv, **kwargs):
        head = str(argv[0]).lower() if argv else ""
        if "powershell" in head:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=300)
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    return run


def _capture_posts(monkeypatch):
    posts: list[tuple[str, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True, "intake_id": "in_test"}

    monkeypatch.setattr(crash_report, "_post_intake", fake_post)
    return posts


def test_clear_timeout_intake_body_has_nick_and_site(tmp_path: Path, monkeypatch):
    job = _setup(tmp_path, monkeypatch)
    posts = _capture_posts(monkeypatch)
    bw.opencode_cleanup_extra_worktrees(
        job, temp_root=tmp_path, run=_timeout_run(job), log_fn=lambda _m: None
    )
    assert len(posts) == 1, posts
    title, body = posts[0]
    assert "fleet-ps1-clear-failed" in title or "fleet-ps1-clear-failed" in body
    assert "site=`fleet-ps1-clear-failed`" in body
    assert "nick: bob-seat-test" in body
    assert "kind: opencode-clear" in body
    assert "job: job" in body
    assert "TimeoutExpired" in body


def test_runtime_failure_context_appended_and_redacted(tmp_path: Path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    posts: list[tuple[str, str]] = []

    def fake_post(title, body, **kw):
        posts.append((title, body))
        return {"ok": True}

    r = runtime_failure.report(
        "bob-worker",
        RuntimeError("boom"),
        site="ctx-test",
        filer_post=fake_post,
        context={
            "nick": "bob-seat-test",
            "kind": "opencode-clear",
            "job": "fr-10048",
            "extra": "GH_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        },
    )
    assert r.get("ok") is True
    assert len(posts) == 1
    body = posts[0][1]
    assert "nick: bob-seat-test" in body
    assert "job: fr-10048" in body
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in body
    assert "<redacted" in body


def test_filing_path_has_no_gh_issue_create():
    for path in (_SCRIPTS / "bob_worker.py", _COMMON / "runtime_failure.py", _COMMON / "crash_report.py"):
        text = path.read_text(encoding="utf-8")
        assert "gh issue create" not in text, path


def test_dedupe_second_clear_failure_skips_post(tmp_path: Path, monkeypatch):
    job = _setup(tmp_path, monkeypatch)
    posts = _capture_posts(monkeypatch)
    run = _timeout_run(job)
    bw.opencode_cleanup_extra_worktrees(job, temp_root=tmp_path, run=run, log_fn=lambda _m: None)
    second = bw.opencode_cleanup_extra_worktrees(
        job, temp_root=tmp_path, run=run, log_fn=lambda _m: None
    )
    assert second == []
    assert len(posts) == 1, posts
