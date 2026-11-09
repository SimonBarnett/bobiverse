"""FR #6301: OpenCode/Copilot fuel rows + agent starts + no n/a flicker.

Parts A/B/C combined. Fixtures never use 82/74/43/75/35.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
STATUS_CS = ROOT / "tray" / "dialogs" / "BobStatus.cs"
OPENCODE_CS = ROOT / "tray" / "dialogs" / "OpencodePaint.cs"
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
WORKER = ROOT / "scripts" / "bob_worker.py"
OPENCODE_FUEL = ROOT.parents[0] / "common" / "scripts" / "opencode_fuel.py"
if not OPENCODE_FUEL.is_file():
    OPENCODE_FUEL = ROOT.parent / "common" / "scripts" / "opencode_fuel.py"

PS = None
for cand in (
    os.environ.get("SystemRoot", r"C:\Windows") + r"\System32\WindowsPowerShell\v1.0\powershell.exe",
    "powershell.exe",
    "pwsh",
):
    if cand and Path(cand).is_file() if "\\" in cand or "/" in cand else True:
        PS = cand
        break


def _ps(script: str) -> str:
    assert PS, "PowerShell required"
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6301_opencode_row_format_left_and_reset():
    """known window -> 'go weekly - 64% left - 2d 5h'; no rem est."""
    script = f"""
. '{HOVER}'
$rec = [pscustomobject]@{{ status='known'; used_pct=36; remaining_pct=64; reset_label='2d 5h'; source='go-zen-usage' }}
$line = Format-BobOpencodeWindowLine -WindowId week -Record $rec
Write-Output $line
"""
    line = _ps(script)
    assert line == "go weekly - 64% left - 2d 5h"
    assert "rem est" not in line
    assert "% used" not in line


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6301_opencode_reset_format_under_24h():
    script = f"""
. '{HOVER}'
$rec = [pscustomobject]@{{ status='known'; used_pct=10; remaining_pct=90; reset_label='5h 12m'; source='go-zen-usage' }}
Format-BobOpencodeWindowLine -WindowId rolling -Record $rec
"""
    assert _ps(script) == "go rolling - 90% left - 5h 12m"


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6301_opencode_missing_uses_error_field():
    script = f"""
. '{HOVER}'
$rec = [pscustomobject]@{{ status='unknown'; used_pct=$null; remaining_pct=$null; reset_label=$null; error='provider unavailable' }}
Format-BobOpencodeWindowLine -WindowId month -Record $rec
"""
    line = _ps(script)
    assert "provider unavailable" in line
    assert line.startswith("go monthly")


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6301_copilot_title_and_zero_left_when_100_used():
    script = f"""
. '{HOVER}'
$pool = [pscustomobject]@{{
  state='ok'; unlimited=$true; used=50; max_recorded_usage=50
  reset_at='2099-01-15T12:00:00Z'; fetched_at='2099-01-01T12:00:00Z'
}}
$line = Format-BobCopilotPoolLine -Pool $pool -Now ([datetime]'2099-01-01T12:00:00Z')
Write-Output $line
$bar = Get-BobCopilotMeterBarPct -Pool $pool -Now ([datetime]'2099-01-01T12:00:00Z')
Write-Output ("BAR=" + $bar)
"""
    out = _ps(script).splitlines()
    line = out[0]
    assert line.startswith("Copilot")
    assert "included unlimited used" not in line.lower()
    assert "100.00% of max" not in line
    assert "0% left" in line
    assert any(x.startswith("BAR=0") for x in out)


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6301_digest_known_survives_local_unstarted_cache(tmp_path: Path):
    """Part C: digest known windows must not flicker to n/a when local cache is unstarted."""
    hover = HOVER.read_text(encoding="utf-8-sig")
    assert "Test-BobOpencodeWindowsPreferDigest" in hover or "prefer digest known" in hover.lower() or "digest known windows" in hover.lower()
    # Behavioral: Format from digest-known record stays known after pack
    script = f"""
. '{HOVER}'
$wins = [pscustomobject]@{{
  rolling = [pscustomobject]@{{ status='known'; used_pct=0; remaining_pct=100; reset_label='4h 0m'; source='go-zen-usage' }}
  week = [pscustomobject]@{{ status='known'; used_pct=0; remaining_pct=100; reset_label='2d 0h'; source='go-zen-usage' }}
  month = [pscustomobject]@{{ status='known'; used_pct=36; remaining_pct=64; reset_label='12d 3h'; source='go-zen-usage' }}
}}
$pack = Format-BobOpencodeWindowLines -FreePct 100 -Windows $wins
$pack.window_lines | ForEach-Object {{ $_ }}
Write-Output ('SUMMARY=' + $pack.summary)
"""
    out = _ps(script)
    assert "n/a" not in out.split("SUMMARY=")[0]
    assert "go rolling - 100% left" in out
    assert "go weekly - 100% left" in out
    assert "go monthly - 64% left" in out


def test_fr6301_opencode_paint_uses_remaining_rgb_not_fixed_blue():
    cs = STATUS_CS.read_text(encoding="utf-8")
    paint = OPENCODE_CS.read_text(encoding="utf-8")
    # Bars carry R/G/B; Status uses them (green→red), not hard-coded 88/166/255 for OpenCode.
    assert "r.Bar.R = b.R" in cs or "Bar.R = b.R" in cs or "row.R" in paint
    assert "Get-BobTrayBarFillRgb" in HOVER.read_text(encoding="utf-8-sig")
    # OpencodePaint parses r/g/b from bar dicts
    assert 'Int(d, "r"' in paint or 'Str(d, "r"' in paint or "row.R" in paint


def test_fr6301_agent_start_entries_have_no_fuel_text():
    worker = WORKER.read_text(encoding="utf-8")
    tray = TRAY_CS.read_text(encoding="utf-8")
    chunk = worker[worker.index("def list_worker_agents") : worker.index("def list_worker_agents") + 3500]
    assert '"reason": ""' in chunk
    assert "UNKNOWN_MENU_REASON" not in chunk
    seed = tray[tray.index("void SeedAgentChoices") : tray.index("void SeedAgentChoices") + 900]
    assert "fuel unknown" not in seed
    assert 'AddAgentChoice(parent, "grok", "Grok"' in seed



def test_fr6301_opencode_models_listed_for_submenu():
    worker = WORKER.read_text(encoding="utf-8")
    assert "opencode_model_menu_rows" in worker or "models" in worker[worker.index("def list_worker_agents") : worker.index("def list_worker_agents") + 3500]
    tray = TRAY_CS.read_text(encoding="utf-8")
    assert "models" in tray[tray.index("void ApplyAgentList") : tray.index("void ApplyAgentList") + 2000]
    assert "BOB_OPENCODE_MODEL" in tray


def test_fr6301_reset_label_from_epoch_compact():
    sys.path.insert(0, str(OPENCODE_FUEL.parent))
    import opencode_fuel

    now = 1_700_000_000_000
    # >24h
    assert opencode_fuel.reset_label_from_epoch_ms(now + 2 * 86400_000 + 5 * 3600_000, now) == "2d 5h"
    # <24h
    assert opencode_fuel.reset_label_from_epoch_ms(now + 5 * 3600_000 + 12 * 60_000, now) == "5h 12m"


def test_fr6301_prefer_digest_helper_exists():
    src = HOVER.read_text(encoding="utf-8-sig")
    assert "function Test-BobOpencodeWindowsHaveKnown" in src or "function Merge-BobOpencodePaintPreferDigest" in src
