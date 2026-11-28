# -*- coding: utf-8 -*-
"""FR #10037: Clear TimeoutExpired must not fleet-ps1-clear-failed."""
from __future__ import annotations

import subprocess
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
Start-Sleep -Seconds 400
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


def test_fr10037_clear_timeout_skips_runtime_failure(tmp_path: Path, monkeypatch):
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
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout") or 300)
        if "rev-parse" in argv:
            return _R(0, str(job / ".git") + "\n")
        return _R(0, "")

    bw.opencode_cleanup_extra_worktrees(
        job, temp_root=tmp_path, run=run, log_fn=logs.append
    )
    assert "fleet-ps1-clear-failed" not in filed, filed
    assert any("skipped:timeout" in x for x in logs), logs


def test_fr10037_source_handles_timeout_before_generic():
    text = Path(bw.__file__).read_text(encoding="utf-8")
    block = text.split("def opencode_cleanup_extra_worktrees", 1)[1].split(
        "return removed\n\n\n_BUSY_HELD_RX", 1
    )[0]
    assert "FR #10037" in block
    assert "except _sp.TimeoutExpired" in block
    assert "skipped:timeout" in block
    timeout_tail = block.split("except _sp.TimeoutExpired", 1)[1].split(
        "except Exception", 1
    )[0]
    assert "runtime_failure.report_message" not in timeout_tail