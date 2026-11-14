"""FR #7250: tray polls pools every 60s; stale after 120s; no updated stamp."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
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


def test_fr7250_named_constants_in_source():
    hover = HOVER.read_text(encoding="utf-8-sig")
    assert "function Get-BobTrayPoolPollSec" in hover
    assert "return 60" in hover[hover.index("function Get-BobTrayPoolPollSec") :][
        :400
    ]
    stale = hover[hover.index("function Get-BobPoolStaleAfterSec") :]
    stale = stale[: stale.index("function Format-BobPoolUpdatedLabel")]
    assert "return 120" in stale
    watch = WATCH.read_text(encoding="utf-8-sig")
    assert "[int]$PollSec = 60" in watch
    docs = DOCS.read_text(encoding="utf-8")
    assert "FR #7250" in docs
    assert "updated HH:mm" in docs  # named as removed
    assert "Get-BobTrayPoolPollSec" in docs


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr7250_ps_constants_and_no_updated_stamp():
    script = f"""
. '{HOVER}'
Write-Output ('POLL=' + (Get-BobTrayPoolPollSec))
Write-Output ('STALE=' + (Get-BobPoolStaleAfterSec))
$lab = Format-BobPoolUpdatedLabel -FetchedAt '2026-11-10T15:30:00Z'
Write-Output ('LAB=' + $(if ($null -eq $lab) {{ 'null' }} else {{ [string]$lab }}))
$now = [datetime]'2026-11-10T10:02:01Z'
$fresh = Get-BobPoolReadingFreshness -FetchedAt '2026-11-10T10:00:00Z' -Now $now
Write-Output ('JUST=' + $fresh.state)
$now2 = [datetime]'2026-11-10T10:01:00Z'
$ok = Get-BobPoolReadingFreshness -FetchedAt '2026-11-10T10:00:00Z' -Now $now2
Write-Output ('OK=' + $ok.state)
$line = Format-BobOpencodeWindowLine -WindowId week -Record ([pscustomobject]@{{
  status='known'; remaining_pct=64; reset_label='2d'; fetched_at='2026-11-10T10:00:00Z'
}}) -Now $now2
Write-Output ('LINE=' + $line)
"""
    out = {ln.split("=", 1)[0]: ln.split("=", 1)[1] for ln in _ps(script).splitlines() if "=" in ln}
    assert out.get("POLL") == "60"
    assert out.get("STALE") == "120"
    assert out.get("LAB") == "null"
    assert out.get("JUST") == "stale"
    assert out.get("OK") == "fresh"
    assert "updated" not in (out.get("LINE") or "")
    assert "64% left" in (out.get("LINE") or "")
