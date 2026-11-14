"""FR #7378: only the [stale] token is red on every pool UsageRow."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _ps(script: str) -> str:
    from winps51 import env_for_powershell_exe

    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
        env=env_for_powershell_exe(),
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7378_split_go_rolling_stale():
    script = f"""
. '{HOVER}'
$p = Split-BobTrayStaleHeading -Heading 'go rolling - [stale]'
$o = [ordered]@{{
  prefix=$p.Prefix; has=[bool]$p.HasStale; suffix=$p.Suffix; tok=$p.Token
}}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["has"] is True
    assert data["tok"] == "[stale]"
    assert data["prefix"] == "go rolling - "
    assert data["suffix"] == ""


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7378_split_copilot_and_xai():
    script = f"""
. '{HOVER}'
$c = Split-BobTrayStaleHeading -Heading 'Copilot - 0% left - 16d 2h [stale]'
$x = Split-BobTrayStaleHeading -Heading 'FLAMINGO unknown (system-profile-skipped) [stale]'
$clean = Split-BobTrayStaleHeading -Heading 'go weekly - 40% left - 2d'
$o = [ordered]@{{
  c_prefix=$c.Prefix; c_has=[bool]$c.HasStale; c_suf=$c.Suffix
  x_prefix=$x.Prefix; x_has=[bool]$x.HasStale
  clean_has=[bool]$clean.HasStale; clean_prefix=$clean.Prefix
}}
$o | ConvertTo-Json -Compress
"""
    data = json.loads(_ps(script).splitlines()[-1])
    assert data["c_has"] is True
    assert data["c_prefix"] == "Copilot - 0% left - 16d 2h "
    assert data["c_suf"] == ""
    assert data["x_has"] is True
    assert data["x_prefix"].startswith("FLAMINGO")
    assert data["clean_has"] is False
    assert data["clean_prefix"] == "go weekly - 40% left - 2d"


def test_fr7378_watch_usage_row_splits_token_not_whole_heading():
    w = WATCH.read_text(encoding="utf-8-sig")
    assert "FR #7378" in w
    assert "Split-BobTrayStaleHeading" in w or "HasStale" in w
    # OpenCode bars still call Add-BobTrayUsageRow (token paint lives inside it).
    assert "Add-BobTrayUsageRow -X 18 -Y $y -Heading ([string]$b.heading)" in w
    # Whole-heading HeadingColor must not be the only stale path for OpenCode.
    assert "function Add-BobTrayUsageRow" in w


def test_fr7378_bobstatus_draws_token_only():
    src = STATUS_CS.read_text(encoding="utf-8")
    assert "DrawHeadingWithStaleToken" in src
    assert "FR #7378" in src
    assert 'const string tok = "[stale]"' in src
    # UsageRow must not paint whole heading via r.Red.
    usage = src[src.index("int UsageRow(") : src.index("int UsageRow(") + 500]
    assert "r.Red ? Red : Fg" not in usage
    assert "DrawHeadingWithStaleToken" in usage


def test_fr7378_hover_exports_split_helper():
    h = HOVER.read_text(encoding="utf-8-sig")
    assert "function Split-BobTrayStaleHeading" in h
    assert "function Get-BobTrayStaleForeColorArgb" in h
