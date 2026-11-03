"""FR #6041: WS-Security wsu:Timestamp + InvalidSecurity mapping."""
from __future__ import annotations

from datetime import datetime, timezone

import priority_wcf as wcf


def _secret() -> str:
    return "FAKE_" + "WCF" + "TS" + "41"


def _dotnet_style_envelope(*, created: str, expires: str, user: str, password: str) -> str:
    """Captured shape of a .NET WCF TransportWithMessageCredential header."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}" xmlns:u="{wcf.WSU_NS}">'
        "<s:Header>"
        f'<o:Security s:mustUnderstand="1" xmlns:o="{wcf.WSSE_NS}">'
        '<u:Timestamp u:Id="_0">'
        f"<u:Created>{created}</u:Created>"
        f"<u:Expires>{expires}</u:Expires>"
        "</u:Timestamp>"
        f'<o:UsernameToken u:Id="uuid-test-1">'
        f"<o:Username>{user}</o:Username>"
        f'<o:Password Type="{wcf.PASSWORD_TEXT_TYPE}">{password}</o:Password>'
        "</o:UsernameToken>"
        "</o:Security>"
        "</s:Header>"
        f'<s:Body><GetVersion xmlns="{wcf.TEMPURI}"></GetVersion></s:Body>'
        "</s:Envelope>"
    )


def test_fr6041_envelope_matches_dotnet_wsu_timestamp():
    secret = _secret()
    now = datetime(2026, 11, 2, 22, 34, 0, tzinfo=timezone.utc)
    env = wcf.build_envelope(
        "GetVersion",
        user="tabula",
        password=secret,
        now=now,
        token_id="uuid-test-1",
        ttl_s=300,
        emit_priority_ns=False,
    )
    created = "2026-11-02T22:34:00.000Z"
    expires = "2026-11-02T22:39:00.000Z"
    want = _dotnet_style_envelope(
        created=created, expires=expires, user="tabula", password=secret
    )
    assert 's:mustUnderstand="1"' in env
    assert f'xmlns:u="{wcf.WSU_NS}"' in env
    assert "<u:Timestamp" in env
    assert f"<u:Created>{created}</u:Created>" in env
    assert f"<u:Expires>{expires}</u:Expires>" in env
    assert 'u:Id="uuid-test-1"' in env
    assert wcf.PASSWORD_TEXT_TYPE in env
    assert secret in env
    for needle in (
        "mustUnderstand",
        "Timestamp",
        "Created",
        "Expires",
        "UsernameToken",
        "PasswordText",
    ):
        assert needle in want and needle in env


def test_fr6041_invalid_security_is_wcf_security_rejected():
    secret = _secret()
    fault = (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>a:InvalidSecurity</faultcode>"
        "<faultstring>An error occurred when verifying security for the message.</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )
    parsed = wcf.parse_soap_response(fault)
    assert parsed["ok"] is False
    assert parsed["error"] == wcf.WCF_SECURITY_REJECTED
    assert "InvalidSecurity" in parsed.get("fault_code", "")

    def fake_post(url, data, headers, timeout_s=30.0):
        assert b"u:Timestamp" in data
        assert b'mustUnderstand="1"' in data
        return 500, fault

    out = wcf.PriorityWcfClient(
        {
            "url": "https://priority.example.invalid",
            "user": "tabula",
        },
        passed_password=secret,
        http_post=fake_post,
        mode="relay",
    ).get_version()
    assert out["error"] == wcf.WCF_SECURITY_REJECTED
    assert secret not in str(out)
    assert out.get("ok") is False
