"""Hostile pins for PR #6042 / FR #6041: TTL, naive UTC, 6039 redaction still on."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import priority_wcf as wcf


def test_mrb6042_naive_now_is_utc_and_ttl_300():
    naive = datetime(2026, 11, 2, 22, 34, 0)
    env = wcf.build_envelope(
        "GetVersion",
        user="tabula",
        password="FAKE_" + "x",
        now=naive,
        token_id="uuid-test-1",
    )
    assert "<u:Created>2026-11-02T22:34:00.000Z</u:Created>" in env
    assert "<u:Expires>2026-11-02T22:39:00.000Z</u:Expires>" in env
    created = datetime(2026, 11, 2, 22, 34, 0, tzinfo=timezone.utc)
    assert created + timedelta(seconds=wcf.TIMESTAMP_TTL_S) == datetime(
        2026, 11, 2, 22, 39, 0, tzinfo=timezone.utc
    )


def test_mrb6042_invalidsecurity_casefold_and_no_secret():
    secret = "FAKE_" + "INVSEC"
    fault = (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>A:INVALIDSECURITY</faultcode>"
        f"<faultstring>pw {secret}</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )
    parsed = wcf.parse_soap_response(fault)
    assert parsed["error"] == wcf.WCF_SECURITY_REJECTED
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula"},
        passed_password=secret,
        http_post=lambda *a, **k: (500, fault),
    ).get_version()
    assert out["error"] == wcf.WCF_SECURITY_REJECTED
    assert secret not in str(out)
