"""FR #9097: compiled WorkerLauncher.Launch retries without BREAKAWAY on Access Denied (5)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

BOB_TRAY = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "bob" / "docs" / "bob-worker.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr9097_workerlauncher_error_access_denied_retry():
    t = _txt(BOB_TRAY)
    assert "ErrorAccessDenied" in t
    assert "const int ErrorAccessDenied = 5" in t
    assert "FR #9097" in t
    # Prefer breakaway, then retry path without CreateBreakawayFromJob.
    launch = t[t.index("FR #8568: prefer breakaway") : t.index("RememberClickedSeat")]
    assert "CreateNewConsole | CreateBreakawayFromJob" in launch.replace(" ", "") or (
        "CreateNewConsole | CreateBreakawayFromJob" in launch
    )
    assert launch.count("CreateProcessW(run, cmd,") >= 2
    assert "err != ErrorAccessDenied" in launch
    assert "int retryFlags = CreateNewConsole" in launch
    assert "CreateBreakawayFromJob" not in launch.split("int retryFlags = CreateNewConsole", 1)[1].split(
        "CreateProcessW(run, cmd,", 1
    )[0]


def test_fr9097_docs_note_compiled_rebuild():
    d = _txt(DOCS)
    assert "FR #9097" in d
    assert "WorkerLauncher.Launch" in d or "bob-tray.exe" in d
    assert "Access Denied" in d
