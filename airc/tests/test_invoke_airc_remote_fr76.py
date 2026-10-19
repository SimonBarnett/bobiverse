"""FR #76: Invoke-AircRemote.ps1 offline SelfTest + smoke construction."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

PS = Path(os.environ.get("AIRC_POWERSHELL") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
SCRIPT = ROOT / "scripts" / "Invoke-AircRemote.ps1"


pytestmark = pytest.mark.skipif(
    os.name != "nt" or not PS.is_file() or not SCRIPT.is_file(),
    reason="FR #76 requires Windows PowerShell + Invoke-AircRemote.ps1",
)


def _run(*extra: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    cmd = [
        str(PS),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def test_selftest_passes():
    r = _run("-SelfTest")
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    assert "SELFTEST PASSED" in r.stdout


def test_whatif_status_prints_privmsg_without_secrets(tmp_path):
    r = _run(
        "-MachineId",
        "marchhare",
        "-Action",
        "Status",
        "-WhatIf",
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    blob = (r.stdout or "") + (r.stderr or "")
    # FR #2570: Status pins id=<8hex> STATUS (not bare STATUS).
    assert "PRIVMSG marchhare_console :id=" in blob and " STATUS" in blob
    assert "password=" not in blob.lower() or "password=***" in blob.lower()


def test_outbox_write_command(tmp_path):
    outbox = tmp_path / "outbox.txt"
    r = _run(
        "-MachineId",
        "tm",
        "-Action",
        "Cmd",
        "-Text",
        "echo ok",
        "-Outbox",
        str(outbox),
    )
    assert r.returncode == 0, r.stdout + "\n" + r.stderr
    text = outbox.read_text(encoding="utf-8")
    # FR #1546: Command/Cmd bodies are prefixed with id=<corr> for reply correlation.
    assert "PRIVMSG tm_console :id=" in text
    assert "cmd: echo ok" in text


def test_fr4813_selftest_wait_writes_in_process():
    """Happy-path DONE wait must not rely on Start-Job (full-suite flake)."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #4813" in text
    start = text.index("$id = 'aabbccdd'")
    end = text.index("Wait-AircRemoteReplies -RepliesJsonl $jsonl -ExpectJobId 'ffffffff'")
    block = text[start:end]
    assert "Add-Content -LiteralPath $jsonl" in block
    assert "Start-Job -ScriptBlock" not in block
    assert "$job = Start-Job" not in block
