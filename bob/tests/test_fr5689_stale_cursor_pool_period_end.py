"""FR #5689: stale cached group period_end must not beat fresh LocalCursorDoc billing end.

When cursor-pools.json by_seat.<seat>.groups.<gid>.period_end is in the past,
Get-BobCursorPoolsForTray -LocalOnly used to overwrite the fresh LocalCursorDoc.period_end,
then Write-BobIrcStatus re-saved the poison stamp every heartbeat. Digest _mask_expired_pools
correctly nulled remaining. Prefer local billing end; refuse to persist/read expired stamps.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "tray" / "src" / "Private" / "Get-BobIrc.ps1"
TRAY = ROOT / "tray"
PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fr5689_select_helper_and_localonly_prefer_local():
    h = _txt(HOVER)
    irc = _txt(IRC)
    assert "FR #5689" in h
    assert "Select-BobCursorPoolBillingPeriodEnd" in h
    assert "Select-BobCursorPoolBillingPeriodEnd" in irc
    assert "Test-BobCursorPoolPeriodEndCurrent" in irc
    fn = h[h.index("function Get-BobCursorPoolsForTray") :]
    # LocalOnly path must not blindly assign cached group period_end over $periodEnd.
    local_only = fn[fn.index("else {") : fn.index("Digest may fill still-null period_end")]
    assert "Select-BobCursorPoolBillingPeriodEnd" in local_only
    assert "$pe = [string]$ge.period_end" not in local_only
    save = irc[irc.index("function Save-BobCursorPoolGroupForSeat") :]
    save = save[: save.index("function Save-BobCursorPoolForSeat")]
    assert "Test-BobCursorPoolPeriodEndCurrent" in save
    assert "never persist an expired period_end" in save or "FR #5689" in save
    read = irc[irc.index("function Read-BobCursorPoolsCache") :]
    read = read[: read.index("function Parse-BobCursorPoolLabel")]
    assert "drop expired group period_end on read" in read or "FR #5689" in read


@needs_ps
def test_fr5689_localonly_publishes_fresh_period_end_over_stale_cache(tmp_path):
    past = _iso(datetime.now(timezone.utc) - timedelta(days=16))
    fresh = _iso(datetime.now(timezone.utc) + timedelta(days=6))
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    cache = {
        "by_seat": {
            "club-madeira": {
                "groups": {
                    "high-cost-models": {
                        "remaining_pct": 100,
                        "period_end": past,
                    },
                    "auto": {
                        "remaining_pct": 57,
                        "period_end": past,
                    },
                }
            }
        }
    }
    (bridge / "cursor-pools.json").write_text(json.dumps(cache), encoding="utf-8")
    body = f"""
$env:BOB_BRIDGE_HOME = '{bridge}'
$local = [pscustomobject]@{{
  period_end = '{fresh}'
  remaining_pct = 57
  cursor_spending_groups = @(
    [pscustomobject]@{{ id = 'high-cost-models'; remaining_pct = 100 }}
    [pscustomobject]@{{ id = 'auto'; remaining_pct = 57 }}
  )
}}
$rows = @(Get-BobCursorPoolsForTray -MachineId 'flamingo' -LocalCursorDoc $local -PcentRows @() -LocalOnly)
$by = @{{}}
foreach ($r in $rows) {{ $by[[string]$r.group_id] = $r }}
[pscustomobject]@{{
  high = [string]$by['high-cost-models'].period_end
  auto = [string]$by['auto'].period_end
  high_rem = $by['high-cost-models'].remaining_pct
  auto_rem = $by['auto'].remaining_pct
}} | ConvertTo-Json -Compress
"""
    script = tmp_path / "t5689.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
        "& (Get-Module BobBridge) {\n" + body + "\n}\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stderr[-1200:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["high"].startswith(fresh[:10]), out
    assert out["auto"].startswith(fresh[:10]), out
    assert int(out["high_rem"]) == 100
    assert int(out["auto_rem"]) == 57
    assert past not in out["high"] and past not in out["auto"]


@needs_ps
def test_fr5689_save_refuses_expired_period_end(tmp_path):
    past = _iso(datetime.now(timezone.utc) - timedelta(days=3))
    fresh = _iso(datetime.now(timezone.utc) + timedelta(days=5))
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    body = f"""
$env:BOB_BRIDGE_HOME = '{bridge}'
Save-BobCursorPoolGroupForSeat -SeatId 'club-madeira' -GroupId 'auto' -RemainingPct 57 -PeriodEnd '{past}'
$c1 = Read-BobCursorPoolsCache
$pe1 = $null
if ($c1.by_seat['club-madeira'].groups.auto.period_end) {{ $pe1 = [string]$c1.by_seat['club-madeira'].groups.auto.period_end }}
Save-BobCursorPoolGroupForSeat -SeatId 'club-madeira' -GroupId 'auto' -RemainingPct 57 -PeriodEnd '{fresh}'
$c2 = Read-BobCursorPoolsCache
$pe2 = [string]$c2.by_seat['club-madeira'].groups.auto.period_end
[pscustomobject]@{{ pe1 = $pe1; pe2 = $pe2; rem = [int]$c2.by_seat['club-madeira'].groups.auto.remaining_pct }} | ConvertTo-Json -Compress
"""
    script = tmp_path / "t5689save.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
        "& (Get-Module BobBridge) {\n" + body + "\n}\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, r.stderr[-1200:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert not out.get("pe1"), out
    assert out["pe2"].startswith(fresh[:10]), out
    assert int(out["rem"]) == 57
