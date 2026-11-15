"""FR #7510: TipForm/Status pool numbers come only from the digest (via tray-digest-pools.json).

Tray polls https://bob.ntsa.uk/bob/v1/report every 60s; no local engine / tray-status
pool fields / Get-BobWeeklyRemaining / Get-CursorAgentUsage / opencode-fuel.json for
Status/TipForm pool paint.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
HELPER = ROOT / "tray" / "tools" / "Update-BobTrayDigestPools.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


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


def _fresh_iso(seconds_ago: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _stale_iso(seconds_ago: int = 300) -> str:
    return _fresh_iso(seconds_ago)


def _fixture_digest(fetched_at: str) -> dict:
    return {
        "machines": {
            "marchhare": {
                "xai_weekly": {
                    "remaining_pct": 71,
                    "account": "FAKE_mh",
                    "fresh": True,
                    "fetched_at": fetched_at,
                    "period_end": "2026-11-21T12:00:00Z",
                },
                "workers": [{"nick": "marchhare-1", "state": "idle"}],
            },
            "flamingo": {
                "xai_weekly": {
                    "remaining_pct": 44,
                    "account": "FAKE_fl",
                    "fresh": True,
                    "fetched_at": fetched_at,
                }
            },
            "redqueen": {
                "xai_weekly": {
                    "remaining_pct": 19,
                    "account": "FAKE_rq",
                    "fresh": True,
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
                    },
                    "week": {
                        "status": "known",
                        "remaining_pct": 60,
                        "used_pct": 40,
                        "reset_label": "in 3d",
                    },
                    "month": {
                        "status": "known",
                        "remaining_pct": 70,
                        "used_pct": 30,
                        "reset_label": "in 12d",
                    },
                },
            }
        },
        "copilot": {
            "remaining": 33,
            "state": "ok",
            "fetched_at": fetched_at,
            "reset_at": "2026-12-01T00:00:00Z",
        },
    }


@needs_ps
def test_fr7510_helper_matches_fixture_digest_exactly(tmp_path: Path):
    fa = _fresh_iso(20)
    digest = _fixture_digest(fa)
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(digest), encoding="utf-8")
    root = tmp_path / "install"
    root.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
if (-not $p) {{ throw 'helper returned null path' }}
Get-Content -LiteralPath $p -Raw -Encoding UTF8
"""
    raw = _ps(script)
    data = json.loads(raw)
    assert data.get("digest_ok") is True
    assert not data.get("digest_error")
    headings = [str(g.get("heading", "")) for g in data.get("grok", [])]
    joined = "\n".join(headings)
    assert "71% left" in joined
    assert "44% left" in joined
    assert "19% left" in joined
    assert "MARCHHARE" in joined.upper()
    assert "FLAMINGO" in joined.upper()
    assert "REDQUEEN" in joined.upper()
    assert "[stale]" not in joined
    assert "33" in str(data.get("copilot_line", ""))
    ids = [str(r.get("id", "")).lower() for r in data.get("digest_pools", [])]
    assert "opencode-go" in ids
    assert "copilot" in ids
    assert data.get("opencode_go") in (55, "55") or "55" in str(data.get("opencode_line", ""))


@needs_ps
def test_fr7510_stale_fetched_at_marks_heading(tmp_path: Path):
    """FR #7580: TipForm digest paint trusts published fresh; old fetched_at alone is not [stale].

    Local age override lived here under FR #7510; Si's digest-only rule (#7580) removed it
    from Update-BobTrayDigestPools. Digest fresh=false still paints [stale] with last %.
    """
    fa = _stale_iso(300)
    digest = _fixture_digest(fa)
    # Explicit published stale (not age invention).
    for mid, node in digest["machines"].items():
        node["xai_weekly"]["fresh"] = False
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(digest), encoding="utf-8")
    root = tmp_path / "install"
    root.mkdir()
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$j = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$heads = @($j.grok | ForEach-Object {{ [string]$_.heading }})
$staleFlags = @($j.grok | ForEach-Object {{ [bool]$_.fuel_stale }})
[ordered]@{{
  heads = $heads
  fuel_stale = $staleFlags
  any_stale_token = [bool](($heads -join "`n") -match '\\[stale\\]')
}} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["any_stale_token"] is True
    assert any(data["fuel_stale"]), data
    # last % kept with the mark (FR #7378 / #7299)
    joined = "\n".join(data["heads"])
    assert "71% left" in joined
    assert "44% left" in joined


@needs_ps
def test_fr7510_engine_killed_wrong_tray_status_still_digest_values(tmp_path: Path):
    """No / wrong tray-status pool write: helper + Status overlay use digest file."""
    fa = _fresh_iso(15)
    digest = _fixture_digest(fa)
    dig_path = tmp_path / "digest.json"
    dig_path.write_text(json.dumps(digest), encoding="utf-8")
    root = tmp_path / "install"
    (root / "run").mkdir(parents=True)
    # Stale/wrong tray-status: invent local 99% that must not win.
    wrong = {
        "v": 1,
        "title": "bob",
        "alert": "none",
        "grok": [
            {
                "heading": "MARCHHARE  -  local-wrong (99%)",
                "known": True,
                "pct": 99,
                "r": 88,
                "g": 166,
                "b": 255,
                "workers": [],
            }
        ],
        "copilot_line": "Copilot - 1% left",
        "opencode_line": "OpenCode  go 1%",
        "digest_pools": [],
    }
    (root / "run" / "tray-status.json").write_text(
        json.dumps(wrong), encoding="utf-8"
    )
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{dig_path}'
$digest = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
$status = Get-Content -LiteralPath (Join-Path '{root}' 'run\\tray-status.json') -Raw -Encoding UTF8 | ConvertFrom-Json
# Prefer digest pools file for paint (same rule as BobStatus Reload).
$paintGrok = @($digest.grok | ForEach-Object {{ [string]$_.heading }})
$paintCopilot = [string]$digest.copilot_line
[ordered]@{{
  digest_path = $p
  paint_grok = $paintGrok
  paint_copilot = $paintCopilot
  status_wrong = [string]$status.grok[0].heading
}} | ConvertTo-Json -Compress -Depth 6
"""
    data = json.loads(_ps(script).splitlines()[-1])
    joined = "\n".join(data["paint_grok"])
    assert "71% left" in joined
    assert "99%" not in joined
    assert "local-wrong" not in joined
    assert "33" in data["paint_copilot"]
    assert "99%" in data["status_wrong"]


@needs_ps
def test_fr7510_digest_unreachable_writes_error_note(tmp_path: Path):
    root = tmp_path / "install"
    root.mkdir()
    bad = tmp_path / "missing-digest.json"
    script = f"""
$ErrorActionPreference = 'Stop'
. '{HOVER}'
. '{DIALOGS}'
$p = Update-BobTrayDigestPools -Root '{root}' -DigestPath '{bad}'
$j = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
[ordered]@{{
  ok = [bool]$j.digest_ok
  err = [string]$j.digest_error
  note = [string]$j.note
}} | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["ok"] is False
    blob = (data.get("err") or "") + " " + (data.get("note") or "")
    assert re.search(r"unreachable|missing|not found|failed|digest", blob, re.I), data


def test_fr7510_pins_helper_and_status_prefer_digest_file():
    assert HELPER.is_file(), "missing Update-BobTrayDigestPools.ps1"
    h = _txt(HOVER)
    assert "function Update-BobTrayDigestPools" in h
    assert "tray-digest-pools.json" in h
    assert "FR #7510" in h

    st = _txt(STATUS_CS)
    assert "tray-digest-pools.json" in st
    assert "FR #7510" in st
    # Prefer digest pools over tray-status pool fields.
    assert "ApplyDigestPoolOverlay" in st or "OverlayDigestPools" in st or "digestPoolsFile" in st

    tray = _txt(TRAY_CS)
    assert "Update-BobTrayDigestPools" in tray
    assert "60000" in tray or "60 * 1000" in tray or "FR #7510" in tray

    d = _txt(DOCS)
    assert "FR #7510" in d
    assert "tray-digest-pools.json" in d


def test_fr7510_pool_paint_path_has_no_local_pool_sources():
    """Status/TipForm pool paint must not call local weekly/Cursor/opencode-fuel readers."""
    h = _txt(HOVER)
    # Format + Select window (display helpers) stay free of local weekly.
    start = h.index("function Format-BobTrayXaiWeeklyRow")
    mid = h.index("function Select-BobTrayXaiWeeklyFromDigestNode")
    end = h.index("\nfunction ", mid + 10)
    window = h[start:end]
    assert "Get-BobWeeklyRemaining" not in window
    assert "Get-CursorAgentUsage" not in window
    assert "opencode-fuel.json" not in window

    upd_start = h.index("function Update-BobTrayDigestPools")
    upd_rest = h[upd_start:]
    upd_end = upd_rest.find("\nfunction ", 10)
    upd = upd_rest if upd_end < 0 else upd_rest[:upd_end]
    # NOTES may name forbidden sources (same pattern as FR #6285); strip comment block.
    upd_code = re.sub(r"<#.*?#>", "", upd, flags=re.S)
    assert "Get-BobWeeklyRemaining" not in upd_code
    assert "Get-CursorAgentUsage" not in upd_code
    assert "opencode-fuel.json" not in upd_code
    assert "peCache" not in upd_code
    assert "Get-BobTrayDigestReportUrl" in upd or "DigestPath" in upd

    # Paint block still digest-only (FR #6285).
    paint = h[h.index("FR #6285: always paint via Format-BobTrayXaiWeeklyRow") :]
    paint = paint[: paint.index("FR #352:")]
    assert "Get-BobWeeklyRemaining" not in paint.replace(
        "Never Format-BobPeerPoolHeading / local Get-BobWeeklyRemaining for this section.",
        "",
    )
    assert "Get-CursorAgentUsage" not in paint
    assert "opencode-fuel.json" not in paint

    st = _txt(STATUS_CS)
    status_load = st[st.index("LoadMerged") : st.index("protected override CreateParams")]
    assert "tray-digest-pools" in st
    assert "digestPoolsFile" in status_load or "OverlayDigestPools" in status_load
    assert "Get-BobWeeklyRemaining" not in status_load
    assert "Get-CursorAgentUsage" not in status_load
    assert "opencode-fuel" not in status_load

    # Watch TipForm rebuild: pool headings from hover digest fields, not local weekly call in rebuild.
    w = _txt(WATCH)
    rebuild = w[w.index("function Rebuild-BobTrayTiles") : w.index("Atomic swap on the TipForm")]
    assert "Get-BobWeeklyRemaining" not in rebuild
    assert "Get-CursorAgentUsage" not in rebuild
    assert "opencode-fuel.json" not in rebuild


def test_fr7510_helper_script_is_file_invokable():
    text = _txt(HELPER)
    assert "Update-BobTrayDigestPools" in text
    assert "Root" in text
    assert "FR #7510" in text
