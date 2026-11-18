# -*- coding: utf-8 -*-
"""FR #8211: Clear exit 0xC000013A (console closed) must not fleet-ps1-clear-failed."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw

_CLEAR_PS1 = """\
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$KeepPath = '',
    [int]$MaxExtraJobTrees = 0,
    [switch]$SkipSeatDisk
)
"""


def _setup_clear(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    (job / ".git").mkdir()
    monkeypatch.setenv("BOB_INSTALL_ROOT", str(tmp_path / "install"))
    clear = tmp_path / "install" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
    clear.parent.mkdir(parents=True)
    clear.write_text(_CLEAR_PS1, encoding="utf-8")
    monkeypatch.setenv("BOB_SCRIPTS_DIR", str(clear.parent))
    bw._FLEET_PS1_MISMATCH_WARNED.clear()
    return job


def test_fr8211_console_close_exit_is_status_control_c():
    assert bw.CONSOLE_CLOSE_EXIT == 0xC000013A
    assert bw.normalize_agent_exit_code(3221225786) == bw.CONSOLE_CLOSE_EXIT
    # Signed Win32 form often seen from subprocess.
    assert bw.normalize_agent_exit_code(-1073741510) == bw.CONSOLE_CLOSE_EXIT


def test_fr8211_clear_console_close_skips_runtime_failure(tmp_path: Path, monkeypatch):
    job = _setup_clear(tmp_path, monkeypatch)

    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    filed: list[str] = []
    logs: list[str] = []

    def _report(component, message, *, site="", **_kw):
        filed.append(site)
        return {"ok": True}

    monkeypatch.setattr("runtime_failure.report_message", _report)

    def run(argv, **kwargs):
        head = str(argv[0]).lower() if argv else ""
        if "powershell" in head:
            return _R(bw.CONSOLE_CLOSE_EXIT, "")
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    out = bw.opencode_cleanup_extra_worktrees(
        job, temp_root=tmp_path, run=run, log_fn=logs.append
    )
    assert out == []
    assert "fleet-ps1-clear-failed" not in filed, filed
    assert any("skipped:console-closed" in x for x in logs), logs


def test_fr8211_clear_real_nonzero_still_reports(tmp_path: Path, monkeypatch):
    job = _setup_clear(tmp_path, monkeypatch)

    class _R:
        def __init__(self, code=0, out=""):
            self.returncode = code
            self.stdout = out
            self.stderr = ""

    filed: list[str] = []
    logs: list[str] = []

    def _report(component, message, *, site="", **_kw):
        filed.append(site)
        return {"ok": True}

    monkeypatch.setattr("runtime_failure.report_message", _report)

    def run(argv, **kwargs):
        head = str(argv[0]).lower() if argv else ""
        if "powershell" in head:
            return _R(1, "boom")
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    bw.opencode_cleanup_extra_worktrees(
        job, temp_root=tmp_path, run=run, log_fn=logs.append
    )
    assert any("failed:exit-1" in x for x in logs), logs
    assert "fleet-ps1-clear-failed" in filed, filed
