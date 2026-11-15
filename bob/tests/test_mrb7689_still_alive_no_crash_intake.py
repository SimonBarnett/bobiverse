"""MRB #7689 hostile pin: still-alive recycle refuse must not crash-intake."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mrb7689_ear_doc_still_alive_no_crash_intake():
    doc = (ROOT / "bob" / "docs" / "bob-ear.md").read_text(encoding="utf-8")
    assert "FR #7688" in doc
    assert "reason=still-alive" in doc or "`reason=still-alive`" in doc
    assert "must not open a tray RuntimeError" in doc
    # Old claim that every still-alive refuse reports to intake is gone.
    assert "still alive, no new seat is started and the failure is reported to intake" not in doc


def test_mrb7689_ps1_still_alive_skips_report_failure():
    ps1 = (ROOT / "bob" / "tray" / "tools" / "BobTrayRecycleSeat.ps1").read_text(
        encoding="utf-8"
    )
    # Product tip lands this; docs PR may merge after. Pin FR marker + no ReportFailure
    # in the still-alive window when the product change is present.
    if "FR #7688" not in ps1:
        return
    i = ps1.index("FR #7688")
    window = ps1[i : i + 450]
    assert "still-alive" in window
    assert "Invoke-BobTrayRecycleSeatReportFailure" not in window
