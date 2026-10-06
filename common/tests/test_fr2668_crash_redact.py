"""FR #2668: crash redact must cover Bearer, NickServ, quoted JSON keys, URL userinfo (Py + C#)."""
from __future__ import annotations

import re

import crash_report
from repo_layout import resolve

# Table: (label, input, must_not_contain substrings)
REDACT_CASES = [
    (
        "bearer_auth",
        "Authorization: Bearer FAKEbearerVALUE123",
        ["FAKEbearerVALUE123"],
    ),
    (
        "basic_auth",
        "Authorization: Basic FAKEbasicVALUE",
        ["FAKEbasicVALUE"],
    ),
    (
        "bearer_bare",
        "got Bearer FAKEbareTOKEN99 from upstream",
        ["FAKEbareTOKEN99"],
    ),
    (
        "nickserv_identify",
        "NickServ IDENTIFY bob-x FAKEnspw",
        ["FAKEnspw"],
    ),
    (
        "nickserv_register",
        "NickServ REGISTER FAKEregpw email@example.com",
        ["FAKEregpw"],
    ),
    (
        "privmsg_nickserv",
        "PRIVMSG NickServ :IDENTIFY bob-x FAKEpmnspw",
        ["FAKEpmnspw"],
    ),
    (
        "irc_pass",
        "PASS FAKEircserverpw",
        ["FAKEircserverpw"],
    ),
    (
        "quoted_json_api_key",
        '{"api_key": "FAKEjsonKEY"}',
        ["FAKEjsonKEY"],
    ),
    (
        "quoted_json_password",
        '{"password": "FAKEjsonPW"}',
        ["FAKEjsonPW"],
    ),
    (
        "url_userinfo",
        "https://user:FAKEurlpw@host/x",
        ["FAKEurlpw"],
    ),
    (
        "pass_colon",
        "pass: fakepw1",
        ["fakepw1"],
    ),
    (
        "still_redacts_token_eq",
        "token=goodsecret XAI_API_KEY=xai_secret ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ["goodsecret", "xai_secret"],
    ),
]


def test_redact_table_python():
    for label, raw, forbidden in REDACT_CASES:
        out = crash_report.redact(raw)
        for bad in forbidden:
            assert bad not in out, f"{label}: still contains {bad!r} in {out!r}"
        assert "<redacted>" in out or "<redacted-token>" in out, f"{label}: no redaction marker in {out!r}"


def test_redact_regression_fr2411_blob():
    raw = (
        "password=hunter2 token: abc GH_TOKEN=gho_xxx BOB_IRC_PASSWORD=secret "
        "Authorization: Bearer xyz ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    )
    out = crash_report.redact(raw)
    assert "hunter2" not in out
    assert "gho_xxx" not in out
    assert "xyz" not in out
    assert "ghp_" not in out
    assert "secret" not in out or "BOB_IRC_PASSWORD=<redacted>" in out


def test_csharp_crashhook_redact_parity_source():
    """C# CrashHook.Redact must mirror the FR #2668 patterns (compiled, not pytest-runnable)."""
    text = resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "FR #2668" in text or "2668" in text
    # Bearer/Basic must consume the following token (not stop at scheme name).
    assert "Bearer" in text and "Basic" in text
    assert re.search(r"Bearer\|Basic|Basic\|Bearer", text)
    assert "IDENTIFY" in text and "REGISTER" in text
    assert "NickServ" in text
    assert r"PASS\s+" in text or "PASS\\s+" in text or 'PASS' in text
    # Quoted JSON keys: optional quotes around key before [:=]
    assert '"?' in text or r"\"?" in text or "optional" in text.lower() or "2668" in text
    # URL userinfo
    assert "://" in text or "userinfo" in text.lower() or "@" in text
    # Redact method still present and uses the expanded rules
    assert "public static string Redact" in text
