"""FR #7372: xAI weekly machine lines have no Grok / Cursor product-pair label."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or "powershell.exe"


def test_fr7372_formatter_source_has_no_grok_cursor_label():
    text = HOVER.read_text(encoding="utf-8")
    fn = text[text.index("function Format-BobTrayXaiWeeklyRow") :]
    fn = fn[: fn.index("\nfunction ", 10)]
    assert "$parts += 'Grok / Cursor'" not in fn
    assert "Grok / Cursor" not in fn


@pytest.mark.skipif(os.name != "nt" or not PS, reason="Windows PowerShell")
def test_fr7372_machine_line_is_id_pct_account_reset_only():
    script = f"""
. '{HOVER}'
$now = [datetime]'2026-11-14T21:00:00Z'
$end = $now.AddDays(6).AddHours(15)
$x = [pscustomobject]@{{
  remaining_pct = 71
  account = 'si@ntsa.uk'
  fresh = $true
  fetched_at = '2026-11-14T21:00:00Z'
  period_end = $end.ToString('o')
}}
# Format-BobResetLabel uses UtcNow unless we pin via period_end relative to now;
# call it with -Now so the heading is deterministic.
$lab = Format-BobResetLabel -PeriodEnd $end -FetchedAt $null -Now $now
$row = Format-BobTrayXaiWeeklyRow -MachineId 'marchhare' -XaiWeekly $x
Write-Output ('HEAD=' + $row.heading)
Write-Output ('LAB=' + $lab)
"""
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    lines = {ln.split("=", 1)[0]: ln.split("=", 1)[1] for ln in r.stdout.splitlines() if "=" in ln}
    head = lines.get("HEAD") or ""
    assert "Grok / Cursor" not in head
    assert "Cursor / Grok" not in head
    assert head.startswith("MARCHHARE  71% left  si@ntsa.uk")
    assert "6 days, 15 hours" in (lines.get("LAB") or "")
    # Formatter uses live UtcNow for reset; still must be machine, pct, account only before any reset token.
    bits = [b for b in head.split("  ") if b]
    assert bits[0] == "MARCHHARE"
    assert bits[1] == "71% left"
    assert bits[2] == "si@ntsa.uk"
    assert "Grok" not in bits
    assert "Cursor" not in bits
