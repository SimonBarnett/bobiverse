"""FR #611: surface intake error bodies; drop permanent HTTP 400 outbox rows."""
from __future__ import annotations

import intake


def test_parse_intake_error_body_extracts_error():
    assert intake.parse_intake_error_body('{"error":"bad_title"}') == "bad_title"
    assert intake.parse_intake_error_body('{"error":"bad_kind"}') == "bad_kind"
    assert intake.parse_intake_error_body("not json") is None
    assert intake.parse_intake_error_body("") is None


def test_outbox_drop_reason_permanent_400_validation():
    good = {"repo": "SimonBarnett/bobiverse", "title": "ok", "kind": "issue"}
    assert intake.outbox_drop_reason(good) is None
    assert (
        intake.outbox_drop_reason(good, http_status=400, error="bad_title") == "bad_title"
    )
    assert (
        intake.outbox_drop_reason(good, http_status=400, error="bad_kind") == "bad_kind"
    )
    assert (
        intake.outbox_drop_reason(good, http_status=400, error="payload_too_large")
        == "payload_too_large"
    )
    assert intake.outbox_drop_reason(good, http_status=400) == "http_400"
    # Local payload already invalid
    assert intake.outbox_drop_reason({"repo": "SimonBarnett/bobiverse", "title": ""}) == "bad_title"
    long_title = "x" * 201
    assert (
        intake.outbox_drop_reason({"repo": "SimonBarnett/bobiverse", "title": long_title})
        == "bad_title"
    )
    assert (
        intake.outbox_drop_reason({"repo": "SimonBarnett/bobiverse", "title": "t", "kind": "nope"})
        == "bad_kind"
    )


def test_validate_payload_bad_title_still_400():
    err, _ = intake.validate_payload(
        {"repo": "SimonBarnett/bobiverse", "title": "", "body": "x"}
    )
    assert err == "bad_title"
    err2, _ = intake.validate_payload(
        {"repo": "SimonBarnett/bobiverse", "title": "y" * 201, "body": "x"}
    )
    assert err2 == "bad_title"


def test_process_intake_bad_title_returns_error_field(tmp_path):
    filer = intake.FakeGitHubFiler()
    result = intake.process_intake(
        tmp_path,
        {"repo": "SimonBarnett/bobiverse", "title": "", "body": "x"},
        filer=filer,
        rate=intake.RateLimiter(per_min=30),
        client_ip="127.0.0.1",
    )
    assert result.status == 400
    assert result.body.get("error") == "bad_title"


def test_report_script_documents_error_surface():
    from pathlib import Path
    from repo_layout import ROOT

    text = (ROOT / "scripts" / "Report-BobiverseIntakeIssue.ps1").read_text(encoding="utf-8-sig")
    for needle in (
        "intake_error",
        "charset=utf-8",
        "GetBytes",
        "bad_title",
        "ErrorDetails",
        "HTTP {0} intake error=",
    ):
        assert needle in text, needle


def test_harvest_flush_documents_permanent_400_drop():
    from repo_layout import ROOT

    text = (ROOT / "scripts" / "Invoke-BobiverseHarvest.ps1").read_text(encoding="utf-8-sig")
    for needle in (
        "PermanentIntakeErrors",
        "http_400",
        "Get-IntakeErrorName",
        "charset=utf-8",
        "GetBytes",
    ):
        assert needle in text, needle


def test_intake_py_is_ascii_or_bom():
    """MRB #626 / FR #2926: intake.py must be ASCII or valid UTF-8 (BOM optional)."""
    from pathlib import Path
    from repo_layout import ROOT

    raw = (ROOT / "scripts" / "intake.py").read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    raw.decode("utf-8")
    assert b"\xe2\x80\xa6" not in raw  # U+2026
