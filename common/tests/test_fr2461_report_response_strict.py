"""FR #2461: Report-BobiverseIntakeIssue must not touch Exception.Response under StrictMode."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Report-BobiverseIntakeIssue.ps1"


def test_report_uses_safe_exception_response_helper():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "Get-ExceptionHttpResponse" in text
    assert "PSObject.Properties['Response']" in text or 'PSObject.Properties["Response"]' in text
    assert "$ErrorRecord.Exception.Response" not in text
    assert "$ex.Response" not in text


def test_get_intake_error_detail_uses_helper():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    start = text.index("function Get-BobiverseIntakeErrorDetail")
    block = text[start : start + 1800]
    assert "Get-ExceptionHttpResponse" in block
    assert ".Exception.Response" not in block
