"""FR #7615: Watch-BobTray / BobTrayDialogs digest GET use Invoke-BobDigestHttpGet.

Companion to FR #7602. PS 5.1 Invoke-WebRequest -TimeoutSec can hang in CloseWait;
these two remaining call sites must use HttpWebRequest Timeout + ReadWriteTimeout.
Generic ids only; no secrets; no real machine names.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "tray" / "tools" / "BobTrayDialogs.ps1"
HELPER = ROOT / "tray" / "src" / "Private" / "Invoke-BobDigestHttpGet.ps1"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr7615_helper_still_uses_httpwebrequest_not_iwr():
    src = _txt(HELPER)
    assert "HttpWebRequest" in src
    assert "ReadWriteTimeout" in src
    assert "Invoke-WebRequest" not in src


def test_fr7615_watch_bob_tray_xai_weekly_uses_helper():
    src = _txt(WATCH)
    start = src.index("function Get-BobTrayMachineXaiWeekly")
    end = src.index("\nfunction ", start + 10)
    body = src[start:end]
    assert "Invoke-BobDigestHttpGet" in body
    assert "FR #7615" in body or "FR #7602" in body
    # No IWR on the digest GET path inside this function.
    assert "Invoke-WebRequest" not in body


def test_fr7615_bob_tray_dialogs_sync_workers_uses_helper():
    src = _txt(DIALOGS)
    start = src.index("function Sync-BobTrayStatusWorkersFromDigest")
    end = src.index("\nfunction ", start + 10)
    body = src[start:end]
    assert "Invoke-BobDigestHttpGet" in body
    assert "FR #7615" in body or "FR #7602" in body
    assert "Invoke-WebRequest" not in body


def test_fr7615_no_banned_machine_names_in_changed_chunks():
    chunks = []
    for path, needle in (
        (WATCH, "function Get-BobTrayMachineXaiWeekly"),
        (DIALOGS, "function Sync-BobTrayStatusWorkersFromDigest"),
    ):
        src = _txt(path)
        start = src.index(needle)
        end = src.index("\nfunction ", start + 10)
        chunks.append(src[start:end].lower())
    blob = "\n".join(chunks)
    banned = ("wal" + "rus", "red" + "queen", "ion" + "os", "flam" + "ingo")
    for name in banned:
        assert name not in blob


def test_fr7615_no_iwr_digest_get_in_tray_tools():
    """Neither tools file should still IWR the report URL for digest GET."""
    for path in (WATCH, DIALOGS):
        src = _txt(path)
        for m in re.finditer(r"Invoke-WebRequest[^\n]+", src):
            line = m.group(0)
            assert "bob/v1/report" not in line.lower()
            assert "Get-BobTrayDigestReportUrl" not in line
