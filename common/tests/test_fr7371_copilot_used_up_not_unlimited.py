"""FR #7371: used-up Copilot premium quota must not paint as unlimited/100%."""
from __future__ import annotations

import json
from pathlib import Path

import copilot_dispatch as cd


# Live MarchHare digest shape (2026-11-14): GitHub flags unlimited + 100% while remaining=0.
USED_UP = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 1937,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": False,
        }
    },
}

PARTIAL = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-12-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 60,
            "entitlement": 100,
            "remaining": 40,
            "percent_remaining": 40.0,
            "unlimited": False,
            "overage_permitted": False,
        }
    },
}

# Genuine unlimited (#5172): remaining=0 + overage_permitted=True.
GENUINE_UNLIMITED = {
    "copilot_plan": "business",
    "quota_reset_date_utc": "2026-11-01T00:00:00.000Z",
    "quota_snapshots": {
        "premium_interactions": {
            "credits_used": 39,
            "entitlement": 0,
            "remaining": 0,
            "percent_remaining": 100.0,
            "unlimited": True,
            "overage_permitted": True,
        }
    },
}


def test_fr7371_parse_used_up_not_unlimited():
    q = cd.parse_user_quota(USED_UP)
    assert q["unlimited"] is False
    assert q["state"] == "exhausted"
    assert q["remaining"] == 0
    assert q["percent_remaining"] == 0
    assert q["used"] == 1937
    assert q["overage_permitted"] is False
    assert q["reset_at"].startswith("2026-12-01")


def test_fr7371_parse_partial_finite():
    q = cd.parse_user_quota(PARTIAL)
    assert q["unlimited"] is False
    assert q["state"] == "ok"
    assert q["remaining"] == 40
    assert q["percent_remaining"] == 40


def test_fr7371_parse_genuine_unlimited_still_ok():
    q = cd.parse_user_quota(GENUINE_UNLIMITED)
    assert q["unlimited"] is True
    assert q["state"] == "ok"


def test_fr7371_pool_for_digest_used_up(tmp_path: Path):
    home = tmp_path / "h"
    home.mkdir()
    cd.refresh_allowance(home, fetch_user=lambda: USED_UP, now=1.0)
    pool = cd.pool_for_digest(home)
    assert pool["unlimited"] is False
    assert pool["state"] == "exhausted"
    assert pool["remaining"] == 0
    assert pool.get("percent_remaining") == 0


def test_fr7371_tray_used_up_zero_not_unlimited():
    hover = (
        Path(__file__).resolve().parents[2]
        / "bob"
        / "tray"
        / "src"
        / "Public"
        / "Get-BobTrayHover.ps1"
    )
    script = f"""
. '{hover}'
$pool = [pscustomobject]@{{
  unlimited = $true
  remaining = 0
  entitlement = 0
  used = 1937
  percent_remaining = 100
  overage_permitted = $false
  state = 'ok'
  reset_at = '2026-12-01T00:00:00.000Z'
  fetched_at = '2026-11-14T21:15:37Z'
}}
$now = [datetime]'2026-11-14T21:16:00Z'
$line = Format-BobCopilotPoolLine -Pool $pool -Now $now
$bar = Get-BobCopilotMeterBarPct -Pool $pool -Now $now
Write-Output ("LINE=" + $line)
Write-Output ("BAR=" + $bar)
"""
    import subprocess
    import sys

    from winps51 import env_for_powershell_exe

    r = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        env=env_for_powershell_exe(),
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    out = r.stdout
    assert "LINE=" in out
    line = [ln for ln in out.splitlines() if ln.startswith("LINE=")][0][5:]
    bar = [ln for ln in out.splitlines() if ln.startswith("BAR=")][0][4:]
    assert "unlimited" not in line.lower()
    assert "0% left" in line
    assert bar.strip() == "0"
