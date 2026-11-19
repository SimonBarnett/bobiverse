"""FR #8338: a full disk must not become a bob-tray crash or hook-failure issue."""
from __future__ import annotations

from pathlib import Path

import crash_report


def test_should_skip_disk_full_messages():
    msg = 'digest pools write failed: There is not enough space on the disk.'
    assert crash_report.should_skip_report("bob-tray", OSError(msg))
    assert crash_report.should_skip_report("bob-tray", None, body="No space left on device")
    assert crash_report.should_skip_report("bob-tray", None, title="ENOSPC")
    assert not crash_report.should_skip_report("bob-tray", RuntimeError("digest fetch timed out"))


def test_report_exception_skips_disk_full_without_post(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_CRASH_SPOOL", str(tmp_path / "spool"))
    monkeypatch.setattr(crash_report, "_gh_search_open_sig", lambda *a, **k: None)

    def boom_post(*_a, **_k):
        raise AssertionError("must not post disk-full")

    try:
        raise OSError("There is not enough space on the disk.")
    except OSError as exc:
        result = crash_report.report_exception(
            "bob-tray", type(exc), exc, exc.__traceback__, filer_post=boom_post
        )
    assert result.get("skipped") is True
    assert list(Path(crash_report.spool_dir()).glob("crash-*.json")) == []


def test_tray_sources_skip_disk_full_before_report():
    root = Path(crash_report.__file__).resolve().parents[2]
    hover = (root / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1").read_text(encoding="utf-8")
    guard = hover.find("Test-BobTrayDiskFullText ($reason")
    report = hover.find("Report-BobDeterministicException -Site 'Update-BobTrayDigestPools'", guard)
    assert guard > 0 and report > guard
    tool = (root / "bob" / "tray" / "tools" / "Update-BobTrayDigestPools.ps1").read_text(encoding="utf-8")
    assert "not enough space on the disk" in tool
    hook = (root / "bob" / "tray" / "dialogs" / "CrashHook.cs").read_text(encoding="utf-8")
    assert "not enough space on the disk" in hook
    assert "ShouldSkipReport(exeName, hookEx)" in hook
