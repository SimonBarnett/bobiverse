"""FR #1910 / #1842: Flush must tolerate missing outbox files and StrictMode-safe Response."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HARVEST = ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1"


def test_fr1910_move_outbox_guards_missing_source():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #1910" in text
    assert "already gone" in text
    # Move-OutboxDropped must Test-Path before Move-Item
    idx = text.index("function Move-OutboxDropped")
    chunk = text[idx : idx + 900]
    assert "Test-Path -LiteralPath $Path" in chunk
    assert "Move-Item -LiteralPath $Path" in chunk
    assert chunk.index("Test-Path -LiteralPath $Path") < chunk.index("Move-Item -LiteralPath $Path")


def test_fr1910_sent_remove_is_guarded():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "another Flush may have archived" in text or "FR #1910" in text
    assert "Remove-Item -LiteralPath $f.FullName" in text
    # SENT path checks existence before remove
    assert "if (Test-Path -LiteralPath $f.FullName)" in text


def test_fr1842_response_via_psobject_properties():
    text = HARVEST.read_text(encoding="utf-8-sig")
    assert "FR #1842" in text
    assert "PSObject.Properties['Response']" in text
    # Must not use bare $ex.Response under StrictMode
    http = text[text.index("function Get-IntakeHttpStatus") : text.index("function Move-OutboxDropped")]
    assert "$ex.Response -and" not in http
    assert "PSObject.Properties['StatusCode']" in http


def test_fr1910_files_end_with_newline():
    assert HARVEST.read_bytes().endswith(b"\n")
    assert Path(__file__).read_bytes().endswith(b"\n")
