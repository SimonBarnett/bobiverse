"""FR #6215: Copilot historical-max % + reset countdown (even when stale)."""
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
STATUS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
COMMON = ROOT.parent / "common" / "scripts" / "copilot_dispatch.py"


def test_helpers_and_labels_exist():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Get-BobCopilotHistoricalMaxPct" in src
    assert "% left" in src  # FR #6301 display
    assert "Format-BobCopilotPoolLine" in src
    # Reset countdown must not be gated only on fresh (FR #6215).
    fmt = src[src.index("function Format-BobCopilotPoolLine") : src.index("function Test-BobPeriodExpired")]
    assert "Format-BobResetLabel" in fmt
    assert "max_recorded_usage" in fmt or "max_recorded" in fmt
    # Must not require -not $isStale before reset.
    assert "-not `$isStale -and `$reset" not in fmt
    assert "Format-BobResetLabel" in fmt
    cd = COMMON.read_text(encoding="utf-8")
    assert "max_recorded_usage" in cd
    assert "def update_max_recorded_usage" in cd
    assert "def historical_max_pct" in cd


def test_python_historical_max_pct_rounding():
    import importlib.util

    spec = importlib.util.spec_from_file_location("copilot_dispatch", COMMON)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.historical_max_pct(1937, 2000) == "96.85"
    assert mod.historical_max_pct(0, 2000) == "0.00"
    assert mod.historical_max_pct(1937, 0) is None
    assert mod.historical_max_pct(1937, None) is None
    assert mod.historical_max_pct(None, 2000) is None
    # usage exceeds recorded max: bump policy yields 100 after update
    doc = {"used": 2100, "max_recorded_usage": 2000}
    mod.update_max_recorded_usage(doc, 2100)
    assert doc["max_recorded_usage"] == 2100
    assert mod.historical_max_pct(2100, doc["max_recorded_usage"]) == "100.00"


def test_pool_for_digest_carries_max_recorded(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("copilot_dispatch", COMMON)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    home = tmp_path
    mod._write_observation(
        home,
        {
            "state": "ok",
            "unlimited": True,
            "used": 1937,
            "max_recorded_usage": 2000,
            "reset_at": "2026-12-01T00:00:00Z",
            "fetched_at": "2026-11-07T11:59:00Z",
            "source": "copilot_internal/user",
        },
    )
    pool = mod.pool_for_digest(home)
    assert pool.get("max_recorded_usage") == 2000
    assert pool.get("used") == 1937


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
        lines.append(
            f"$line = Format-BobCopilotPoolLine -Pool $pool -Now '{now_iso}' -ForceStale"
        )
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
def test_format_unlimited_with_historical_max_and_reset():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 1937,
            "max_recorded_usage": 2000,
            "fetched_at": "2026-11-07T11:59:00Z",
            "reset_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    # FR #6301: 1937/2000 ~ 97% used => 3% left; reset countdown kept.
    assert "Copilot - 3% left" in line
    assert "reset" in line or "d" in line  # compact reset label
    assert "[stale" not in line
    assert "included" not in line.lower()
    assert "of max recorded" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_stale_still_shows_reset_and_max_pct():
    """Stale marker stays; reset countdown still paints when reset_at is future."""
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 1937,
            "max_recorded_usage": 2000,
            "fetched_at": "2026-11-02T11:00:00Z",  # ~5d old
            "reset_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    assert "stale" in line.lower()
    assert "3% left" not in line
    assert "included" not in line.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_zero_usage_zero_pct():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 0,
            "max_recorded_usage": 2000,
            "fetched_at": "2026-11-07T11:59:00Z",
            "reset_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    assert "Copilot - 100% left" in line
    assert "of max recorded" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_missing_denominator_no_pct():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 1937,
            "fetched_at": "2026-11-07T11:59:00Z",
            "reset_at": "2026-12-01T00:00:00Z",
        },
        now,
    )
    # No max_recorded_usage => cannot compute % left.
    assert line.startswith("Copilot - unknown") or "unknown" in line
    assert "of max recorded" not in line
    assert "n/a%" not in line
    assert "Infinity" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_zero_denominator_no_pct():
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 10,
            "max_recorded_usage": 0,
            "fetched_at": "2026-11-07T11:59:00Z",
        },
        now,
    )
    assert "of max recorded" not in line


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell formatter")
def test_format_usage_above_max_shows_100_after_client_bump_field():
    """Display uses provided max; chair bumps max before publish when usage exceeds."""
    now = "2026-11-07T12:00:00Z"
    line = _ps_format(
        {
            "state": "ok",
            "unlimited": True,
            "used": 2100,
            "max_recorded_usage": 2100,
            "fetched_at": "2026-11-07T11:59:00Z",
        },
        now,
    )
    assert "Copilot - 0% left" in line
    assert "of max recorded" not in line


def test_status_still_uses_formatter_line():
    src = STATUS.read_text(encoding="utf-8-sig")
    assert "SelectCopilotLine" in src
    assert "CopilotLine" in src


def test_watch_uses_format_bob_copilot_pool_line():
    w = WATCH.read_text(encoding="utf-8-sig")
    assert "Format-BobCopilotPoolLine" in w


def test_no_copilot_enable_in_fr_scope():
    """Display-only: hover formatter must not flip dispatch / fuel enable flags."""
    src = HOVER.read_text(encoding="utf-8-sig")
    fmt = src[src.index("function Format-BobCopilotPoolLine") : src.index("function Test-BobPeriodExpired")]
    assert "BOB_FUEL_COPILOT" not in fmt
    assert "set_allowance" not in fmt.lower()
