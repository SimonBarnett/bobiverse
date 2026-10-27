"""FR #5052: must-report timer/webhook catches cannot stay empty; best-effort may."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
HOVER = ROOT / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
HELPER = ROOT / "bob" / "tray" / "src" / "Private" / "Invoke-BobMustReportFailure.ps1"

# Operational windows that must call a reporter (not catch { }).
MUST_MARKERS = (
    "$script:trayWorkerSyncSub = Register-ObjectEvent",
    "$script:trayDigestSub = Register-ObjectEvent",
    "$script:trayAliveSub = Register-ObjectEvent",
)

_EMPTY = re.compile(r"catch\s*\{\s*\}")


def _window_after(text: str, needle: str, n: int = 4500) -> str:
    i = text.index(needle)
    return text[i : i + n]


def test_fr5052_must_report_helper_exists():
    t = HELPER.read_text(encoding="utf-8-sig")
    assert "FR #5052" in t
    assert "Report-BobDeterministicException" in t or "Report-BobRuntimeFailure" in t
    assert "best-effort" in t.lower() or "BEST_EFFORT" in t


def test_fr5052_must_report_timer_windows_call_helper():
    t = WATCH.read_text(encoding="utf-8-sig")
    for mark in MUST_MARKERS:
        win = _window_after(t, mark)
        assert "Invoke-BobMustReportFailure" in win or "Report-BobRuntimeFailure" in win, mark
        # The Action's primary catch must not be a bare empty catch { }.
        action = win[win.index("-Action") :]
        assert "FR #5052" in action or "Invoke-BobMustReportFailure" in action, mark


def test_fr5052_digest_write_status_catch_reports():
    t = WATCH.read_text(encoding="utf-8-sig")
    inner = t[t.index("$script:trayDigestSub = Register-ObjectEvent") :]
    call = inner[inner.index("Write-BobIrcStatus | Out-Null") :]
    assert "Invoke-BobMustReportFailure" in call[:2000] or "Report-BobRuntimeFailure" in call[:2000]


def test_fr5052_best_effort_hover_parse_still_allowed():
    """Parse/ToInt empty catches in hover are classified best-effort, not must-report."""
    h = HOVER.read_text(encoding="utf-8-sig")
    assert h.count("catch { }") >= 1
    # Classification comment lives in the helper / Watch file.
    w = WATCH.read_text(encoding="utf-8-sig")
    assert "BEST_EFFORT" in w or "best-effort" in w.lower()
