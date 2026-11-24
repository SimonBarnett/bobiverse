# -*- coding: utf-8 -*-
"""FR #9589: Weights Refresh models — fix CLI discover timeouts; surface per-CLI reasons."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import REPO

WIN = sys.platform == "win32"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
WEIGHTS = REPO / "bob" / "tray" / "dialogs" / "WeightsForm.cs"
CLIENT = REPO / "bob" / "tray" / "dialogs" / "BobModelsClient.cs"
TRAY = REPO / "bob" / "tray" / "dialogs" / "BobTray.cs"
BUILD = REPO / "bob" / "scripts" / "Build-BobDialogs.ps1"


def test_fr9589_sources_pin_discover_hardening():
    c = CLIENT.read_text(encoding="utf-8-sig")
    w = WEIGHTS.read_text(encoding="utf-8-sig")
    t = TRAY.read_text(encoding="utf-8-sig")

    assert "IsBlockedDiscoverPath" in c
    assert "WindowsApps" in c
    assert "RedirectStandardInput = false" in c
    assert "StandardError.ReadToEnd" in c
    assert "EffectiveDiscoverTimeoutMs" in c
    assert "BOB_MODELS_DISCOVER_TIMEOUT_MS" in c
    assert "Programs" in c and "opencode" in c
    assert "WinGet" in c and "Links" in c
    assert "ClassifyListingFailure" in c
    assert "auth_required" in c
    assert 'ComSpec' in c or "cmd.exe" in c

    assert "FormatDiscoverFailureStatus" in w
    assert "DumpDiscoverSummary" in w
    assert "grok=" in w and "cursor=" in w and "opencode=" in w

    assert "--dump-weights-discover" in t
    assert "DumpDiscoverSummary" in t


def test_fr9589_classify_auth_required():
    """Pure source pin: auth stderr maps to auth_required (logic in ClassifyListingFailure)."""
    c = CLIENT.read_text(encoding="utf-8-sig")
    assert 'IndexOf("authentication required"' in c or "authentication required" in c
    assert 'return "auth_required"' in c


def test_fr9589_blocked_windowsapps_path():
    c = CLIENT.read_text(encoding="utf-8-sig")
    assert 'IndexOf("\\\\WindowsApps\\\\"' in c or "WindowsApps" in c


@pytest.mark.skipif(not (WIN and CSC.is_file() and PS), reason="needs Windows csc and powershell")
def test_fr9589_fake_cli_discover_counts(tmp_path: Path):
    """Fake CLI stdout → discover total > 0; timeout path logged as reason=timeout."""
    out_dir = tmp_path / "dlg"
    r = subprocess.run(
        [
            PS,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD),
            "-RepoRoot",
            str(REPO),
            "-OutDir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    tray_exe = out_dir / "bob-tray.exe"
    assert tray_exe.is_file()

    fake_dir = tmp_path / "fake-cli"
    fake_dir.mkdir()
    grok = fake_dir / "fake-grok.cmd"
    oc = fake_dir / "fake-opencode.cmd"
    cur = fake_dir / "fake-agent.cmd"
    hang = fake_dir / "hang.cmd"
    grok.write_text(
        "@echo off\r\necho Available models:\r\necho   - grok-4-fake\r\n",
        encoding="ascii",
    )
    oc.write_text(
        "@echo off\r\necho opencode/deepseek-v4.1-flash-free\r\n",
        encoding="ascii",
    )
    cur.write_text(
        "@echo off\r\necho composer-fake\r\n",
        encoding="ascii",
    )
    hang.write_text(
        "@echo off\r\nping -n 60 127.0.0.1 >nul\r\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    env["BOB_GROK_EXE"] = str(grok)
    env["BOB_OPENCODE_EXE"] = str(oc)
    env["BOB_CURSOR_AGENT"] = str(cur)
    env["BOB_MODELS_DISCOVER_TIMEOUT_MS"] = "15000"

    dump = tmp_path / "discover.txt"
    p = subprocess.run(
        [str(tray_exe), "--dump-weights-discover", str(dump), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )
    assert dump.is_file(), p.stdout + p.stderr
    text = dump.read_text(encoding="utf-8")
    assert "total\t" in text
    # At least grok + opencode should parse; cursor uses grok parser (composer-fake ok).
    lines = {ln.split("\t")[0]: ln for ln in text.splitlines() if "\t" in ln}
    assert "grok" in lines
    assert "opencode" in lines
    assert "\tok\t" in lines["grok"] or lines["grok"].endswith("\tok\t1") or "\t1" in lines["grok"]
    total_line = [ln for ln in text.splitlines() if ln.startswith("total\t")][0]
    total = int(total_line.split("\t")[1])
    assert total >= 2, text
    assert p.returncode == 0

    # Timeout path: point grok at hang.cmd with a short budget.
    env2 = env.copy()
    env2["BOB_GROK_EXE"] = str(hang)
    env2["BOB_MODELS_DISCOVER_TIMEOUT_MS"] = "3000"
    # Keep other CLIs working so total may still be >0; grok reason must be timeout.
    dump2 = tmp_path / "discover-timeout.txt"
    p2 = subprocess.run(
        [str(tray_exe), "--dump-weights-discover", str(dump2), "--no-engine"],
        capture_output=True,
        text=True,
        timeout=90,
        env=env2,
    )
    assert dump2.is_file(), p2.stdout + p2.stderr
    text2 = dump2.read_text(encoding="utf-8")
    assert "grok\ttimeout\t" in text2, text2
