"""FR #7580: tray pool rows paint digest as published (no local staleness).

Tray process polls https://bob.ntsa.uk/bob/v1/report every 60s into
run/tray-digest-pools.json. Values and [stale] match the digest document;
no age-based override. Fetch failure keeps last rows and reports once.
Generic host ids only (no real machine names in fixtures).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
HELPER = ROOT / "tray" / "tools" / "Update-BobTrayDigestPools.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")

# FR #7580: no real fleet machine names in tests.
HOST_A = "host-a"
HOST_B = "host-b"
HOST_C = "host-c"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


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


def _digest(fetched_at: str, *, fresh: bool = True, pct_a: int = 48, err_a: str | None = None) -> dict:
    xa = {
        "remaining_pct": pct_a,
        "account": "FAKE_a",
        "fresh": fresh,
        "fetched_at": fetched_at,
        "period_end": "2026-11-21T12:00:00Z",
        "xai_auth": "ok",
    }
    if err_a:
        xa["error"] = err_a
        xa["xai_auth"] = "expired" if "login-expired" in err_a else xa["xai_auth"]
    return {
        "machines": {
            HOST_A: {
                "xai_weekly": xa,
                "workers": [{"nick": f"{HOST_A}-1", "state": "idle"}],
            },
            HOST_B: {
                "xai_weekly": {
                    "remaining_pct": 71,
                    "account": "FAKE_b",
                    "fresh": fresh,
                    "fetched_at": fetched_at,
                }
            },
            HOST_C: {
                "xai_weekly": {
                    "remaining_pct": 19,
                    "account": "FAKE_c",
                    "fresh": fresh,
                    "fetched_at": fetched_at,
                }
            },
        },
        "fleet_pools": {
            "opencode-go": {
                "remaining": 55,
                "fetched_at": fetched_at,
                "windows": {
                    "rolling": {
                        "status": "known",
                        "remaining_pct": 55,
                        "used_pct": 45,
                        "reset_label": "in 2h",
                    }
                },
            }
        },
        "copilot": {
            "remaining": 33,
            "state": "ok",
            "fresh": fresh,
            "fetched_at": fetched_at,
            "reset_at": "2026-12-01T00:00:00Z",
        },
    }


@needs_ps
def test_fr7580_old_fetched_at_trusts_digest_fresh_true(tmp_path: Path):
    """Local age must not mark [stale] when digest publishes fresh=true."""
    fa = _iso(600)  # 10 min old — would be stale under FR #7510 local age
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(_digest(fa, fresh=True, pct_a=48)), encoding="utf-8")
    root = tmp_path / "install"
    root.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$j = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$heads = @($j.grok | ForEach-Object {{ [string]$_.heading }})
[ordered]@{{
  ok = [bool]$j.digest_ok
  heads = $heads
  any_stale = [bool](($heads -join "`n") -match '\\[stale\\]')
  fuel_stale = @($j.grok | ForEach-Object {{ [bool]$_.fuel_stale }})
  copilot = [string]$j.copilot_line
}} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["ok"] is True
    joined = "\n".join(data["heads"])
    assert "48% left" in joined
    assert "71% left" in joined
    assert data["any_stale"] is False, data
    assert not any(data["fuel_stale"]), data
    assert "[stale]" not in data["copilot"]
    assert "33" in data["copilot"]
    assert HOST_A.upper() in joined.upper()
    assert HOST_B.upper() in joined.upper()


@needs_ps
def test_fr7580_digest_fresh_false_keeps_pct_with_stale_token(tmp_path: Path):
    fa = _iso(30)
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(_digest(fa, fresh=False, pct_a=61)), encoding="utf-8")
    root = tmp_path / "install"
    root.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$j = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$heads = @($j.grok | ForEach-Object {{ [string]$_.heading }})
[ordered]@{{
  heads = $heads
  any_stale = [bool](($heads -join "`n") -match '\\[stale\\]')
  fuel_stale = @($j.grok | ForEach-Object {{ [bool]$_.fuel_stale }})
}} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    joined = "\n".join(data["heads"])
    assert "61% left" in joined
    assert data["any_stale"] is True
    assert all(data["fuel_stale"]), data


@needs_ps
def test_fr7580_fetch_fail_keeps_last_rows_and_flags_unreachable(tmp_path: Path):
    fa = _iso(20)
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(_digest(fa, fresh=True, pct_a=48)), encoding="utf-8")
    root = tmp_path / "install"
    (root / "run").mkdir(parents=True)
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p1 = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$before = Get-Content -LiteralPath $p1 -Raw -Encoding UTF8 | ConvertFrom-Json
$missing = Join-Path '{tmp_path}' 'no-such-digest.json'
$p2 = Update-BobTrayDigestPools -Root '{root}' -DigestPath $missing
$after = Get-Content -LiteralPath $p2 -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{{
  before_ok = [bool]$before.digest_ok
  after_ok = [bool]$after.digest_ok
  note = [string]$after.note
  err = [string]$after.digest_error
  before_heads = @($before.grok | ForEach-Object {{ [string]$_.heading }})
  after_heads = @($after.grok | ForEach-Object {{ [string]$_.heading }})
  after_copilot = [string]$after.copilot_line
}} | ConvertTo-Json -Compress -Depth 6
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["before_ok"] is True
    assert data["after_ok"] is False
    blob = (data.get("note") or "") + " " + (data.get("err") or "")
    assert re.search(r"unreachable|missing|not found|failed|digest", blob, re.I), data
    assert data["after_heads"], "must keep last grok rows"
    assert data["after_heads"] == data["before_heads"]
    assert "48% left" in "\n".join(data["after_heads"])
    assert "33" in (data.get("after_copilot") or "")


@needs_ps
def test_fr7580_wrong_tray_status_ignored_digest_wins(tmp_path: Path):
    fa = _iso(15)
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(_digest(fa, fresh=True, pct_a=48)), encoding="utf-8")
    root = tmp_path / "install"
    (root / "run").mkdir(parents=True)
    wrong = {
        "v": 1,
        "title": "bob",
        "grok": [
            {
                "heading": "HOST-A  -  local-wrong (99%)",
                "known": True,
                "pct": 99,
                "fuel_stale": True,
                "workers": [],
            }
        ],
        "copilot_line": "Copilot - 1% left",
    }
    (root / "run" / "tray-status.json").write_text(json.dumps(wrong), encoding="utf-8")
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$digest = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$heads = @($digest.grok | ForEach-Object {{ [string]$_.heading }})
[ordered]@{{ heads = $heads; copilot = [string]$digest.copilot_line }} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    joined = "\n".join(data["heads"])
    assert "48% left" in joined
    assert "99%" not in joined
    assert "local-wrong" not in joined
    assert "33" in data["copilot"]


def test_fr7580_pins_as_published_and_fetch_fail_report():
    h = _txt(HOVER)
    assert "AsPublished" in h or "-AsPublished" in h
    upd_start = h.index("function Update-BobTrayDigestPools")
    upd_rest = h[upd_start:]
    upd_end = upd_rest.find("\nfunction ", 10)
    upd = upd_rest if upd_end < 0 else upd_rest[:upd_end]
    assert "AsPublished" in upd
    # Must not force local age stale before Format in the digest paint path.
    assert "Force age-based stale before Format" not in upd
    assert "FR #7580" in upd

    tray = _txt(TRAY_CS)
    assert "RefreshDigestPools" in tray
    assert "60000" in tray
    assert "CrashHook.Report" in tray
    assert "digest" in tray.lower() and (
        "digest-fetch" in tray.lower()
        or "digest_ok" in tray
        or "DigestFetch" in tray
        or "digest fetch" in tray.lower()
    )

    st = _txt(STATUS_CS)
    assert "OverlayDigestPools" in st or "LoadMerged" in st
    assert "tray-digest-pools.json" in st

    d = _txt(DOCS)
    assert "FR #7580" in d
    assert "as published" in d.lower() or "no local" in d.lower()


def test_fr7580_fixtures_use_generic_host_ids_only():
    """Acceptance: fixtures use generic host-a/b/c ids only."""
    assert HOST_A == "host-a"
    assert HOST_B == "host-b"
    assert HOST_C == "host-c"
    # Digest builder keys must be the generic hosts.
    sample = _digest(_iso(10))
    assert set(sample["machines"]) == {HOST_A, HOST_B, HOST_C}
