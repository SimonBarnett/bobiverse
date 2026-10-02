"""t785u: MarchHare's own Grok weekly pool is reported (digest, keyed 'marchhare') and a stale reading is not painted as current.

Root cause (live MarchHare 2026-10-02): the Grok CLI only logs 'billing: fetched credits config' while it is used.
The last event on MarchHare was 2026-09-29 19:19Z (period end 2026-09-29 23:41Z, 8% left). After the period rolled:
  * Get-BobWeeklyRemaining kept returning 8% + a PAST period_end (worker: 'grok available pct=8'),
  * the tray (Resolve-BobTrayLivePeriod) hid pct AND reset for an expired period -> blank 'Grok account' row,
  * the digest carried weekly=8 + a past reset, which the chair cleared -> machines.marchhare.weekly = '' (n/a).
Fix: roll the reading to the current weekly period (pct unmeasured = null, reset = next boundary, stale = true).
The 'alert: watcher' state came from a legacy job watcher (Watch-BobJobs.ps1) that the MSI does not ship.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import test_cursor_pools_any_machine as base  # noqa: E402  (fixtures + the bob -> digest harness)

import bobreport  # noqa: E402
import registered_machines as rm  # noqa: E402

TRAY, PS, needs_ps = base.TRAY, base.PS, base.needs_ps


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _billing_log(path: Path, period_end: datetime, used_pct: float = 92.0) -> None:
    ev = {"ts": _iso(period_end - timedelta(hours=4)).replace("+00:00", "Z"), "src": "shell", "ver": "1.0.41", "lvl": "info",
          "msg": "billing: fetched credits config",
          "ctx": {"config": {"creditUsagePercent": used_pct,
                             "currentPeriod": {"type": "USAGE_PERIOD_TYPE_WEEKLY",
                                               "start": _iso(period_end - timedelta(days=7)), "end": _iso(period_end)}}}}
    path.write_text(json.dumps({"ts": "2026-01-01T00:00:00Z", "msg": "noise"}) + "\n" + json.dumps(ev) + "\n", encoding="utf-8")


def _ps_json(tmp_path: Path, body: str, env: dict | None = None):
    f = tmp_path / "t785.ps1"
    f.write_text("$ErrorActionPreference='Stop'\n"
                 f"Import-Module '{TRAY / 'src' / 'BobBridge.psd1'}' -Force -DisableNameChecking\n"
                 "& (Get-Module BobBridge) {\n" + body + "\n} | ConvertTo-Json -Compress -Depth 6\n", encoding="utf-8")
    r = subprocess.run([PS, "-NoProfile", "-File", str(f)], env=dict(os.environ, **(env or {})), capture_output=True,
                       text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-800:]
    out = r.stdout.strip().splitlines()
    return json.loads(out[-1]) if out else None


@needs_ps
def test_expired_weekly_reading_is_rolled_to_the_current_period_not_reported_as_8_percent(tmp_path):
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=3)
    log = tmp_path / "unified.jsonl"
    _billing_log(log, end)
    w = _ps_json(tmp_path, f"Get-BobWeeklyRemaining -LogPath '{log}'")
    assert w["remaining_pct"] is None and w["stale"] is True            # never invent a % for a new period
    assert w["last_remaining_pct"] == 8                                   # the old reading is kept, labelled
    nxt = datetime.fromisoformat(w["period_end"].replace("Z", "+00:00"))
    assert nxt > now and (nxt - end) % timedelta(days=7) == timedelta(0) and nxt - now <= timedelta(days=7)


@needs_ps
def test_current_weekly_reading_passes_through_unchanged(tmp_path):
    now = datetime.now(timezone.utc)
    log = tmp_path / "unified.jsonl"
    _billing_log(log, now + timedelta(days=2))
    w = _ps_json(tmp_path, f"Get-BobWeeklyRemaining -LogPath '{log}'")
    assert w["remaining_pct"] == 8 and not w.get("stale")


@needs_ps
def test_availability_never_says_available_8_percent_for_an_ended_period(tmp_path):
    now = datetime.now(timezone.utc)
    auth = "([pscustomobject]@{allow_access=$true;fetched_at=([datetime]::UtcNow.ToString('o'));subscription_tier_display='x'})"
    expired = ("([pscustomobject]@{remaining_pct=8;period_end='" + _iso(now - timedelta(days=3)) +
               "';format='legacy-1.0.40';kind='weekly'})")
    a = _ps_json(tmp_path, f"Get-BobGrokAvailability -Weekly {expired} -Auth {auth}")
    assert a["remaining_pct"] is None and a["state"] == "stale" and a["reason"] == "period-end-past"
    log = tmp_path / "unified.jsonl"
    _billing_log(log, now - timedelta(days=3))
    a = _ps_json(tmp_path, f"Get-BobGrokAvailability -Weekly (Get-BobWeeklyRemaining -LogPath '{log}') -Auth {auth}")
    assert a["state"] == "available" and a["reason"] == "period-rolled-unmeasured" and a["remaining_pct"] is None
    cur = ("([pscustomobject]@{remaining_pct=8;period_end='" + _iso(now + timedelta(days=2)) + "';format='legacy-1.0.40'})")
    a = _ps_json(tmp_path, f"Get-BobGrokAvailability -Weekly {cur} -Auth {auth}")
    assert a["state"] == "available" and a["remaining_pct"] == 8


def _post_with_log(tmp_path: Path, log: Path) -> dict:
    # base._bob_post builds the env itself; run the same harness with BOB_WEEKLY_LOG pointing at the fixture log.
    old = os.environ.get("BOB_WEEKLY_LOG")
    os.environ["BOB_WEEKLY_LOG"] = str(log)
    try:
        return base._bob_post(tmp_path, base.IONOS_FIXTURE)
    finally:
        if old is None:
            os.environ.pop("BOB_WEEKLY_LOG", None)
        else:
            os.environ["BOB_WEEKLY_LOG"] = old


@needs_ps
def test_digest_carries_marchhares_own_grok_figure_keyed_by_machine(tmp_path):
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=2)
    log = tmp_path / "unified.jsonl"
    _billing_log(log, end)
    p = _post_with_log(tmp_path, log)
    assert p["machine"] == "marchhare" and p["weekly"] == 8 and p["period_end"].startswith(end.strftime("%Y-%m-%dT%H:%M"))
    home = tmp_path / "home"
    home.mkdir()
    rm.save_registered(home, {"marchhare", "win-mpre8vi4u6u"})
    assert bobreport.apply_callback(home, p, "Jeeves").ok
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert ent["weekly"] == 8 and ent["period_end"].startswith(end.strftime("%Y-%m-%dT%H:%M"))


@needs_ps
def test_digest_for_a_stale_grok_reading_carries_the_rolled_reset_and_no_fake_percent(tmp_path):
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=3)
    log = tmp_path / "unified.jsonl"
    _billing_log(log, end)
    p = _post_with_log(tmp_path, log)
    assert p["machine"] == "marchhare"
    assert "weekly" not in p                                              # not the old 8
    nxt = datetime.fromisoformat(p["period_end"].replace("Z", "+00:00"))
    assert nxt > now                                                      # a reset that is in the future
    home = tmp_path / "home"
    home.mkdir()
    rm.save_registered(home, {"marchhare", "win-mpre8vi4u6u"})
    assert bobreport.apply_callback(home, p, "Jeeves").ok
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert ent.get("weekly") in (None, "") and datetime.fromisoformat(ent["period_end"].replace("Z", "+00:00")) > now


@needs_ps
def test_watcher_alert_only_for_an_installed_watcher(tmp_path):
    root = tmp_path / "root"
    (root / "tools").mkdir(parents=True)
    assert _ps_json(tmp_path, f"Test-BobWatcherInstalled -Root '{root}'") is False
    (root / "tools" / "Watch-BobJobs.ps1").write_text("# stub", encoding="utf-8")
    assert _ps_json(tmp_path, f"Test-BobWatcherInstalled -Root '{root}'") is True
    stall = ("function Get-BobHealth { [pscustomobject]@{ watcher_up = $false; last_seen_age_sec = $null; last_seen = $null } }\n"
             "function Get-BobBuilds { @() }\n"
             "%s\n"
             "$seen = @{}; @(Get-BobStallAlerts -Seen $seen) | Where-Object { $_ -match 'watcher_down' } | ForEach-Object { [string]$_ }\n")
    none = _ps_json(tmp_path, stall % "function Test-BobWatcherInstalled { $false }")
    assert not none                                                       # not installed -> no 'alert: watcher'
    some = _ps_json(tmp_path, stall % "function Test-BobWatcherInstalled { $true }")
    assert some and "watcher_down" in json.dumps(some)                    # installed + not running -> still alerts

@needs_ps
def test_stale_local_reading_borrows_the_same_account_figure_from_a_seat_mate_for_the_same_period(tmp_path):
    now = datetime.now(timezone.utc)
    end = (now + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    stale = f"([pscustomobject]@{{stale=$true;remaining_pct=$null;period_end='{end}'}})"
    seats = "@([pscustomobject]@{id='ntsa';machines=@('marchhare','ce-priority-dev1')})"
    wk = "@{'ce-priority-dev1'=88}"
    same = "@{'ce-priority-dev1'='" + end + "'}"
    other = "@{'ce-priority-dev1'='" + (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z") + "'}"
    call = "Resolve-BobSeatMateWeekly -MachineId 'marchhare' -LocalWeek %s -Seats %s -WeeklyBy %s -PeriodEndBy %s"
    assert _ps_json(tmp_path, call % (stale, seats, wk, same)) == 88      # same account, same period -> same pool
    assert _ps_json(tmp_path, call % (stale, seats, wk, other)) is None    # a different period is not this week's figure
    cur = f"([pscustomobject]@{{stale=$false;remaining_pct=8;period_end='{end}'}})"
    assert _ps_json(tmp_path, call % (cur, seats, wk, same)) is None       # a current local reading stays authoritative


@needs_ps
def test_seat_cache_drops_last_periods_percent_when_the_local_reading_is_stale(tmp_path):
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    env = {"BOB_BRIDGE_HOME": str(bridge), "BOB_MACHINE_ID": "marchhare"}
    old, new = "2026-09-29T23:41:45.639212+00:00", "2026-10-06T23:41:45.6392120Z"
    _ps_json(tmp_path, f"Save-BobSeatPeriodEnd -MachineId 'marchhare' -PeriodEnd '{old}' -SeatId 'ntsa' -Weekly 8; 1", env)
    c = json.loads((bridge / "seat-period-end.json").read_text(encoding="utf-8-sig"))
    assert c["weekly_by_machine"]["marchhare"] == 8 and c["weekly_by_seat"]["ntsa"] == 8
    _ps_json(tmp_path, f"Save-BobSeatPeriodEnd -MachineId 'marchhare' -PeriodEnd '{new}' -SeatId 'ntsa' -Weekly $null -ClearWeekly; 1", env)
    c = json.loads((bridge / "seat-period-end.json").read_text(encoding="utf-8-sig"))
    assert "marchhare" not in c["weekly_by_machine"] and "ntsa" not in c["weekly_by_seat"]
    assert c["by_machine"]["marchhare"] == new                             # the new reset is kept


def test_chair_drops_last_periods_weekly_when_a_machine_rolls_without_a_new_figure(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    rm.save_registered(home, {"marchhare"})
    old = "2026-09-29T23:41:45.639212+00:00"
    assert bobreport.apply_callback(home, {"op": "merge", "machine": "marchhare", "weekly": 8, "period_end": old}, "Jeeves").ok
    assert bobreport.load_digest(home)["machines"]["marchhare"]["weekly"] == 8
    new = "2026-10-06T23:41:45.639212+00:00"
    assert bobreport.apply_callback(home, {"op": "merge", "machine": "marchhare", "period_end": new}, "Jeeves").ok
    ent = bobreport.load_digest(home)["machines"]["marchhare"]
    assert "weekly" not in ent and ent["period_end"] == new                # no 8% beside next week's reset
    assert bobreport.apply_callback(home, {"op": "merge", "machine": "marchhare", "weekly": 97, "period_end": new}, "Jeeves").ok
    assert bobreport.load_digest(home)["machines"]["marchhare"]["weekly"] == 97
