"""FR #5050: tray 30s digest timer catch must report, not swallow."""
from __future__ import annotations

from pathlib import Path

WATCH = Path(__file__).resolve().parents[1] / "tray" / "tools" / "Watch-BobTray.ps1"
DET = Path(__file__).resolve().parents[1] / "tray" / "src" / "Private" / "Report-BobDeterministicException.ps1"
RF = Path(__file__).resolve().parents[2] / "common" / "scripts" / "Report-BobRuntimeFailure.ps1"


def test_fr5050_digest_timer_reports_not_empty_catch():
    t = WATCH.read_text(encoding="utf-8-sig")
    inner = t[t.index("$script:trayDigestSub = Register-ObjectEvent") :]
    call = inner[inner.index("Write-BobIrcStatus | Out-Null") :]
    assert "FR #5050" in call[:2500] or "FR #5052" in call[:2500]
    assert "Report-BobRuntimeFailure" in call[:2500] or "Invoke-BobMustReportFailure" in call[:2500]


def test_fr5050_report_helpers_use_intake():
    det = DET.read_text(encoding="utf-8-sig")
    assert "Report-BobRuntimeFailure" in det or "runtime_failure" in det or "Report-BobiverseIntakeIssue" in det
    rf = RF.read_text(encoding="utf-8")
    assert "runtime_failure" in rf
    assert "FR #5050" in rf
