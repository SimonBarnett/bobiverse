"""FR #9011: bob-tray NotifyIcon stays clickable — digest/WMI off the WinForms pump."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAY_CS = ROOT / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "docs" / "bob-tray-dialogs.md"
EVIDENCE = ROOT / "docs" / "bob-9011-tray-notifyicon-clicks.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_digest_refresh_not_sync_on_ctor_ui_thread():
    text = _txt(TRAY_CS)
    assert "FR #9011" in text
    assert "digestPoolsBusy" in text
    assert "never WaitForExit on the WinForms ctor/UI thread" in text
    assert "digestPoolsTimer = new System.Threading.Timer(delegate { RefreshDigestPools(); }, null, 0, 60000);" in text
    ctor = text.split("aliveTimer = new System.Threading.Timer", 1)[1].split("flash.Start();", 1)[0]
    # Timer callback may name RefreshDigestPools; forbid a bare sync call on its own line.
    assert "\n            RefreshDigestPools();\n" not in ctor


def test_watchdog_queued_off_forms_timer():
    text = _txt(TRAY_CS)
    assert "QueueWatchdog" in text
    assert "watchdogBusy" in text
    assert "watchdog.Tick += delegate { QueueWatchdog(); };" in text
    assert "ThreadPool.QueueUserWorkItem" in text


def test_digest_refresh_busy_gate():
    text = _txt(TRAY_CS)
    assert "Interlocked.Exchange(ref digestPoolsBusy, 1)" in text
    assert "finally { System.Threading.Interlocked.Exchange(ref digestPoolsBusy, 0); }" in text


def test_docs_name_9011_pump_rule():
    assert "FR #9011" in _txt(DOCS)
    assert "NotifyIcon" in _txt(DOCS)
    assert EVIDENCE.is_file()
    assert "WaitForExit" in _txt(EVIDENCE)
