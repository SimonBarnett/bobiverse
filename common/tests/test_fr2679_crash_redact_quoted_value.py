"""FR #2679: crash redact must consume quoted multi-word JSON secret values (Py + C#)."""
from __future__ import annotations

import re

import crash_report
from repo_layout import resolve

# Table: (label, input, must_not_contain)
MULTIWORD_CASES = [
    (
        "json_password_spaces",
        '{"password": "FAKE with spaces"}',
        ["FAKE with spaces", "with spaces", "FAKE"],
    ),
    (
        "json_secret_spaces",
        '{"secret": "alpha beta gamma"}',
        ["alpha beta gamma", "beta gamma", "alpha"],
    ),
    (
        "json_api_key_spaces",
        '{"api_key": "key part two"}',
        ["key part two", "part two"],
    ),
    (
        "json_password_spaces_trailing",
        '{"password": "FAKE with spaces", "ok": 1}',
        ["FAKE with spaces", "with spaces"],
    ),
    (
        "json_password_spaced_colon",
        '{ "password" : "multi word secret" }',
        ["multi word secret", "word secret"],
    ),
]


def test_fr2679_multiword_quoted_json_redacted():
    for label, raw, forbidden in MULTIWORD_CASES:
        out = crash_report.redact(raw)
        for bad in forbidden:
            assert bad not in out, f"{label}: still contains {bad!r} in {out!r}"
        assert "<redacted>" in out, f"{label}: no redaction marker in {out!r}"


def test_fr2679_bare_single_token_still_redacts():
    """Bare pass:/password= stay single-token (do not eat the next field)."""
    out = crash_report.redact("password=singleToken next=keepme")
    assert "singleToken" not in out
    assert "password=<redacted>" in out
    assert "next=keepme" in out


def test_fr2679_pass_colon_single_token_safe():
    out = crash_report.redact("pass: fakepw1 other stuff")
    assert "fakepw1" not in out
    assert "other stuff" in out


def test_fr2679_regression_single_token_json():
    """Single-token quoted JSON from FR #2668 must keep working."""
    out = crash_report.redact('{"password": "FAKEjsonPW"}')
    assert "FAKEjsonPW" not in out
    assert "<redacted>" in out


def test_fr2679_csharp_secretkv_quoted_value_alternate():
    """C# SecretKvRe must prefer quoted values before bare single-token class (FR #2679)."""
    text = resolve("third_party/bob-tray/dialogs/CrashHook.cs").read_text(encoding="utf-8-sig")
    assert "2679" in text
    # Quoted-value alternate: ""[^""]*"" before the bare token class
    assert '""[^""]*""' in text
