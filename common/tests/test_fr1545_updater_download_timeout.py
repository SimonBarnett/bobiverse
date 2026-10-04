"""FR #1545: updater download timeout + curl fallback; Airc Fleet wrapper updates on start."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from repo_layout import ROOT

S = ROOT / "scripts"
UPD = S / "Update-BobiverseService.ps1"
FLEET = ROOT / "airc" / "scripts" / "Start-AircConsole-Fleet.ps1"
START = ROOT / "airc" / "scripts" / "Start-AircConsole.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
win = pytest.mark.skipif(os.name != "nt" or not PS, reason="needs Windows PowerShell")
REPO = "SimonBarnett/bobiverse"


def test_fr1545_get_asset_has_timeout_retry_curl():
    t = UPD.read_text(encoding="utf-8-sig")
    assert "FR #1545" in t
    assert "download-try" in t
    assert "method=curl" in t
    assert "--max-time" in t
    assert "download-failed" in t
    assert "TimeoutSec" in t


def test_fr1545_fleet_wrapper_delegates_service_mode():
    assert FLEET.is_file(), FLEET
    t = FLEET.read_text(encoding="utf-8-sig")
    assert "FR #1545" in t
    assert "Start-AircConsole.ps1" in t
    assert "ServiceMode" in t
    assert "Update-BobiverseService" in t or "self-update" in t
    # Must not launch python directly (old hang path).
    assert "airc_console_service.py" not in t


def test_fr1545_start_airc_still_updates_in_service_mode():
    t = START.read_text(encoding="utf-8-sig")
    assert "Update-BobiverseService.ps1" in t
    assert "if ($ServiceMode)" in t


@win
def test_fr1545_curl_max_time_fails_closed_on_blackhole(tmp_path):
    """curl --max-time (same flags as Get-Asset) fails closed against a non-responsive port."""
    curl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
    assert curl.is_file()
    # Bind then close so the port is free — connect may RST quickly; use TEST-NET-1 blackhole instead.
    dest = tmp_path / "stall.bin"
    t0 = time.time()
    r = subprocess.run(
        [
            str(curl),
            "-sSL",
            "--fail",
            "--connect-timeout",
            "2",
            "--max-time",
            "5",
            "-o",
            str(dest),
            "http://192.0.2.1:9/stall",  # TEST-NET-1 / discard — no route to host or timeout
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.time() - t0
    assert r.returncode != 0
    assert elapsed < 20
    assert "--max-time" in UPD.read_text(encoding="utf-8-sig")


@win
def test_fr1545_apply_local_asset_still_works(tmp_path):
    """Local AllowLocalAssets path still copies without curl."""
    root = tmp_path / "bob"
    root.mkdir()
    (root / "VERSION").write_text("0.1.20\n", encoding="ascii")
    state = tmp_path / "state"
    msi = tmp_path / "bob-0.1.21.msi"
    payload = b"MZ-fake-msi-payload-for-fr1545"
    msi.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    sha = tmp_path / "bob-0.1.21.msi.sha256"
    sha.write_text(f"{digest}  bob-0.1.21.msi\n", encoding="ascii")
    plan = {
        "tag": "v0.1.21",
        "version": "0.1.21",
        "msiName": "bob-0.1.21.msi",
        "msiUrl": str(msi),
        "shaUrl": str(sha),
    }
    plan_path = state / "plan.json"
    state.mkdir()
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    # Mode Apply with VerifyOnly + AllowLocalAssets
    args = [
        PS,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(UPD),
        "-Product",
        "bob",
        "-InstallRoot",
        str(root),
        "-StateDir",
        str(state),
        "-Mode",
        "Apply",
        "-PlanFile",
        str(plan_path),
        "-AllowLocalAssets",
        "-VerifyOnly",
        "-DelaySeconds",
        "0",
    ]
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    log = (state / "update.log").read_text(encoding="utf-8") if (state / "update.log").is_file() else ""
    assert p.returncode == 0, (p.stdout, p.stderr, log)
    assert "sha256-verified" in log or "download-ok" in log or "verify-only" in log
