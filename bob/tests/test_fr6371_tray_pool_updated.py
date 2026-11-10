"""FR #6371: tray pool tiles show reading updated time (and stale) from fetched_at."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def _ps(script: str) -> str:
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    return (r.stdout or "").strip()


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6371_updated_only_when_no_reset():
    """Reading with fetched_at and no reset -> updated HH:MM, no countdown."""
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-10T10:05:00Z'
$rec = [pscustomobject]@{{
  status='known'; used_pct=0; remaining_pct=100; reset_label=$null
  fetched_at='2026-11-10T10:00:00Z'; error='reset unavailable'
}}
$line = Format-BobOpencodeWindowLine -WindowId week -Record $rec -Now $now
Write-Output $line
"""
    line = _ps(script)
    assert line.startswith("go weekly - 100% left")
    assert "updated " in line
    # Local HH:MM from 10:00Z depends on machine TZ; stamp shape only.
    assert __import__("re").search(r"updated \d{1,2}:\d{2}", line), line
    assert "reset unavailable" not in line
    # No countdown segment: after "% left" comes updated (not Nd/Hh).
    after = line.split("100% left", 1)[1]
    assert "updated" in after
    assert not __import__("re").search(r"-\s*\d+d\b", after)
    assert not __import__("re").search(r"-\s*\d+h\b", after)


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6371_reset_kept_and_updated_shown():
    """Reading with reset_label keeps countdown and also shows updated time."""
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-10T10:05:00Z'
$rec = [pscustomobject]@{{
  status='known'; used_pct=36; remaining_pct=64; reset_label='2d 5h'
  fetched_at='2026-11-10T10:00:00Z'
}}
$line = Format-BobOpencodeWindowLine -WindowId week -Record $rec -Now $now
Write-Output $line
"""
    line = _ps(script)
    assert "64% left" in line
    assert "2d 5h" in line
    assert "updated " in line
    assert __import__("re").search(r"updated \d{1,2}:\d{2}", line), line


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6371_stale_when_fetched_older_than_threshold():
    """Fetched older than default 15m threshold paints stale."""
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-10T10:20:00Z'
$rec = [pscustomobject]@{{
  status='known'; used_pct=0; remaining_pct=100; reset_label=$null
  fetched_at='2026-11-10T10:00:00Z'
}}
$line = Format-BobOpencodeWindowLine -WindowId rolling -Record $rec -Now $now
Write-Output $line
$fresh = Get-BobPoolReadingFreshness -FetchedAt '2026-11-10T10:00:00Z' -Now $now
Write-Output ('STATE=' + $fresh.state)
Write-Output ('AGE=' + $fresh.age_s)
"""
    out = _ps(script).splitlines()
    line = out[0]
    assert "updated " in line
    assert "[stale" in line.lower() or " stale" in line.lower()
    assert any(x.startswith("STATE=stale") for x in out), out
    assert any(x.startswith("AGE=1200") for x in out), out


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6371_helper_updated_label_local_hhmm():
    script = f"""
. '{HOVER}'
$lab = Format-BobPoolUpdatedLabel -FetchedAt '2026-11-10T15:30:00Z' -Now ([datetime]'2026-11-10T15:31:00Z')
Write-Output $lab
"""
    lab = _ps(script)
    assert lab.startswith("updated ")
    assert __import__("re").match(r"updated \d{1,2}:\d{2}$", lab), lab


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr6371_copilot_line_includes_updated():
    script = f"""
. '{HOVER}'
$pool = [pscustomobject]@{{
  state='ok'; unlimited=$true; used=10; max_recorded_usage=50
  reset_at='2099-01-15T12:00:00Z'; fetched_at='2099-01-01T12:00:00Z'
}}
$line = Format-BobCopilotPoolLine -Pool $pool -Now ([datetime]'2099-01-01T12:00:00Z')
Write-Output $line
"""
    line = _ps(script)
    assert "updated " in line
    assert "0% left" in line or "% left" in line


def test_fr6371_docs_mention_updated_stamp():
    docs = (ROOT / "docs" / "bob-tray-dialogs.md").read_text(encoding="utf-8")
    assert "FR #6371" in docs or "updated HH:MM" in docs or "updated HH:mm" in docs.lower()
    hover = HOVER.read_text(encoding="utf-8-sig")
    assert "Format-BobPoolUpdatedLabel" in hover
    assert "Get-BobPoolReadingFreshness" in hover
