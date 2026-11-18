"""FR #7595: tray pool rows keep last % and timer; [stale] sits right after the %.

Header age comes from the digest ts. A fresh digest must not say
"snapshot is N min old" or "tray not polling?". Generic ids only.
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
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")

HOST = "box-a"


def _ps(script: str, timeout: int = 90) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
    return (r.stdout or "").strip()


def _iso(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_fr7595_status_header_uses_digest_ts_not_status_mtime():
    src = STATUS_CS.read_text(encoding="utf-8-sig")
    assert "tray not polling" not in src
    assert "ApplyDigestHeaderAge" in src
    assert "digest_ts" in src


@needs_ps
def test_fr7595_stale_opencode_and_xai_keep_pct_timer_order(tmp_path: Path):
    """Exact order: % left [stale], then account, then the reset. Bars stay."""
    now = datetime.now(timezone.utc)
    dig = {
        "ts": int(now.timestamp()),
        "stale": False,
        "machines": {
            HOST: {
                "xai_weekly": {
                    "remaining_pct": 46,
                    "account": "FAKE_pool",
                    "fresh": False,
                    "fetched_at": _iso(4000),
                    "period_end": "2026-11-21T12:00:00Z",
                }
            }
        },
        "fleet_pools": {
            "opencode-go": {
                "remaining": 72,
                "windows": {
                    "rolling": {
                        "status": "known",
                        "fresh": True,
                        "remaining_pct": 80,
                        "reset_label": "1h 2m",
                        "fetched_at": _iso(9000),
                    },
                    "week": {
                        "status": "stale",
                        "fresh": False,
                        "remaining_pct": 72,
                        "reset_label": "5h 56m",
                        "fetched_at": _iso(9000),
                    },
                    "month": {
                        "status": "stale",
                        "fresh": False,
                        "remaining_pct": 0,
                        "reset_label": "4d",
                        "period_end": "2026-12-01T00:00:00Z",
                        "fetched_at": _iso(9000),
                    },
                },
            }
        },
        "copilot": {
            "remaining": 12,
            "state": "ok",
            "fresh": False,
            "fetched_at": _iso(9000),
            "reset_at": "2026-11-21T18:00:00Z",
        },
    }
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(dig), encoding="utf-8")
    root = tmp_path / "install"
    (root / "run").mkdir(parents=True)
    # Old engine snapshot must not supply the painted numbers or the header phrase.
    status = {
        "note": "snapshot is 40 min old (tray not polling?)",
        "grok": [{"heading": "WRONG  1% left  other@example.invalid", "known": True, "pct": 1}],
        "opencode_window_lines": ["go weekly - 1% left"],
        "opencode_line": "OpenCode  go 1%",
    }
    (root / "run" / "tray-status.json").write_text(json.dumps(status), encoding="utf-8")
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$j = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$heads = @($j.grok | ForEach-Object {{ [string]$_.heading }})
$bars = @($j.opencode_bars | ForEach-Object {{ $_.id + '=' + [string]$_.known + ':' + [string]$_.pct + ':' + [string]$_.heading }})
[ordered]@{{
  digest_ok = [bool]$j.digest_ok
  digest_ts = $j.digest_ts
  note = [string]$j.note
  heads = $heads
  known = @($j.grok | ForEach-Object {{ [bool]$_.known }})
  pct = @($j.grok | ForEach-Object {{ [int]$_.pct }})
  windows = @($j.opencode_window_lines)
  bars = $bars
  copilot = [string]$j.copilot_line
}} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["digest_ok"] is True
    assert data["note"] in ("", None)
    assert int(data["digest_ts"]) > 0
    assert "snapshot is" not in json.dumps(data)
    assert "tray not polling" not in json.dumps(data)
    assert "other@example.invalid" not in json.dumps(data)
    head = "\n".join(data["heads"])
    assert "46% left [stale]" in head
    stale_at = head.index("46% left [stale]")
    acct_at = head.index("FAKE_pool")
    assert stale_at < acct_at
    assert head.index("[stale]") < acct_at
    assert "hour" in head or "minute" in head or "day" in head
    # FR #6285 / #7595: heading keeps last %; bar_pct is null while stale => known=false, pct=0.
    assert data["known"] == [False]
    assert data["pct"] == [0]
    windows = data["windows"]
    assert "go weekly - 72% left [stale] - 5h 56m" in windows
    assert "go rolling - 80% left - 1h 2m" in windows
    assert not any("rolling" in w and "[stale]" in w for w in windows)
    month = [w for w in windows if w.startswith("go monthly")]
    assert month and "[stale]" not in month[0]
    assert "0% left" in month[0]
    week_bar = [b for b in data["bars"] if b.startswith("week=")]
    assert week_bar and week_bar[0].startswith("week=True:72:")
    cop = data["copilot"]
    assert "12% left [stale]" in cop
    assert cop.index("12% left [stale]") < cop.index("-", cop.index("[stale]"))
