"""FR #6148: Copilot systray freshness marker + always-present line."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
MOCK_HOME = ROOT / "docs" / "mocks" / "digest-fuel" / "home.html"
MOCK_ERROR = ROOT / "docs" / "mocks" / "digest-fuel" / "error.html"
MOCK_ERROR_LEGACY = ROOT / "mocks" / "error.html"


def test_format_helpers_exist():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Get-BobCopilotFreshness" in src
    assert "function Format-BobCopilotPoolLine" in src
    assert "ForceStale" in src
    assert "900" in src
    assert "[stale" in src


def test_watch_always_shows_copilot_unknown_fallback():
    w = WATCH.read_text(encoding="utf-8-sig")
    sec = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Copilot  unknown" in sec
    assert "Format-BobCopilotPoolLine" in sec
    # FIX #6180: escape `[` in -like; TitleColor paints stale red (RightColor alone never did).
    assert "TitleColor" in sec
    assert "`[stale" in sec or "``[stale" in w
    hdr = w[w.index("function Add-BobTraySectionHeader") : w.index("function Set-BobTrayHelpTip")]
    assert "[System.Drawing.Color]$TitleColor" in hdr
    assert "TitleColor.A" in hdr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_stale_despite_future_resume_at():
    """FIX #6180: future resume_at must not force fresh when fetched_at is aged."""
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "exhausted",
            "remaining": 0,
            "fetched_at": "2026-11-07T11:00:00Z",
            "resume_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    assert "[stale" in line


def test_status_reages_copilot_deadline():
    src = STATUS.read_text(encoding="utf-8-sig")
    assert "CopilotFreshUntil" in src
    assert "CopilotStaleLine" in src
    assert "SelectCopilotLine" in src
    assert "copilot_fresh_until" in src
    assert "lastPaintedCopilot" in src


def test_dialogs_snapshot_carries_stale_fields():
    src = DIALOGS.read_text(encoding="utf-8-sig")
    assert "copilot_stale_line" in src
    assert "copilot_fresh_until" in src


def _ps_format(pool: dict, now_iso: str, force_stale: bool = False) -> str:
    pool_json = json.dumps(pool)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f". '{HOVER.as_posix()}'",
        "$pool = @'",
        pool_json,
        "'@ | ConvertFrom-Json",
    ]
    if force_stale:
        lines.append(f"$line = Format-BobCopilotPoolLine -Pool $pool -Now '{now_iso}' -ForceStale")
    else:
        lines.append(f"$line = Format-BobCopilotPoolLine -Pool $pool -Now '{now_iso}'")
    lines.append("Write-Output $line")
    script = "\n".join(lines) + "\n"
    fd, name = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    Path(name).write_text(script, encoding="utf-8")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", name],
            capture_output=True,
            text=True,
            timeout=90,
        )
    finally:
        Path(name).unlink(missing_ok=True)
    if r.returncode != 0:
        raise AssertionError((r.stderr or "") + (r.stdout or ""))
    return (r.stdout or "").strip().splitlines()[-1].strip()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_fresh_unlimited():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 39,
            "fetched_at": "2026-11-07T11:55:00Z",
            "reset_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    assert line.startswith("Copilot  unlimited, 39 used")
    assert "[stale" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_stale_by_age():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "remaining": 140,
            "fetched_at": "2026-11-07T11:00:00Z",
        },
        now,
    )
    assert "[stale" in line
    assert "140 remaining" in line
    assert "reset" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_missing_fetched_at_stale():
    line = _ps_format({"state": "ok", "remaining": 5}, "2026-11-07T12:00:00Z")
    assert "[stale]" in line
    assert "5 remaining" in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_null_pool_unknown():
    fd, name = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    Path(name).write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f". '{HOVER.as_posix()}'",
                "Write-Output (Format-BobCopilotPoolLine -Pool $null)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", name],
            capture_output=True,
            text=True,
            timeout=90,
        )
    finally:
        Path(name).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1].strip() == "Copilot  unknown"


def test_digest_fuel_mocks_have_copilot_shapes():
    home = MOCK_HOME.read_text(encoding="utf-8")
    err = MOCK_ERROR.read_text(encoding="utf-8")
    assert "Copilot" in home
    assert "Formatter line: Copilot  unlimited" in home or "unlimited" in home.lower()
    assert "stale" in err.lower()
    assert "Formatter line: Copilot  [stale" in err or "not current" in err


def test_legacy_mocks_mention_copilot_or_stale_when_present():
    if MOCK_ERROR_LEGACY.is_file():
        t = MOCK_ERROR_LEGACY.read_text(encoding="utf-8")
        if "Copilot" in t:
            assert "stale" in t.lower()
