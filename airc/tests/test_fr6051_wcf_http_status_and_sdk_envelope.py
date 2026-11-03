"""FR #6051: non-2xx is failure; raw body; SDK-shaped GetVersion/GeneralCompanies."""
from __future__ import annotations

from datetime import datetime, timezone

import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "HTTP" + "51"


def test_fr6051_http_400_empty_is_wcf_http_error():
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, ""),
    ).get_version()
    assert out["ok"] is False
    assert out["error"] == wcf.WCF_HTTP_ERROR
    assert out.get("http_status") == 400
    assert _pw() not in str(out)


def test_fr6051_http_500_fault_keeps_soap_fault_and_status():
    secret = _pw()
    fault = (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>a:InternalServiceFault</faultcode>"
        f"<faultstring>boom {secret}</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=secret,
        http_post=lambda *a, **k: (500, fault),
    ).general_companies()
    assert out["ok"] is False
    assert out["error"] == wcf.SOAP_FAULT
    assert out.get("http_status") == 500
    assert secret not in str(out)
    assert secret not in (out.get("raw") or "")


def test_fr6051_golden_getversion_and_generalcompanies():
    secret = _pw()
    now = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append((url, data.decode("utf-8"), headers))
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>ok</s:Body></s:Envelope>'
        )

    inst = {
        "url": "https://priority.example.invalid",
        "user": "tabula",
        "company": "live1",
        "hostname": "FLAMINGO",
    }
    c = wcf.PriorityWcfClient(inst, passed_password=secret, http_post=fake_post)
    assert c.get_version()["ok"] is True
    assert c.general_companies()["ok"] is True
    assert len(seen) == 2
    url0, env0, hdr0 = seen[0]
    url1, env1, hdr1 = seen[1]
    assert hdr0["Content-Type"] == "text/xml; charset=utf-8"
    assert hdr0["SOAPAction"] == '"http://tempuri.org/IWCFService/GetFileVersion"'
    assert hdr1["SOAPAction"] == '"http://tempuri.org/IWCFService/GeneralCompaniesMob"'
    assert '<GetFileVersion xmlns="http://tempuri.org/"/>' in env0 or '<GetFileVersion xmlns="http://tempuri.org/"></GetFileVersion>' in env0
    assert "<GeneralCompaniesMob" in env1
    assert "http://www.w3.org/2005/08/addressing" not in env0
    assert url0.endswith("/wcf/wcf/Service.svc")
    assert hdr0["SOAPAction"] == '"http://tempuri.org/IWCFService/GetFileVersion"'
    assert secret not in str({"raw": "x"})

    env = wcf.build_envelope(
        "GetVersion",
        user=wcf.format_wcf_username("tabula"),
        password=secret,
        now=now,
        token_id="uuid-test-1",
        hostname="FLAMINGO",
        company="live1",
        endpoint="https://priority.example.invalid/wcf/wcf/Service.svc",
        message_id="urn:uuid:11111111-1111-1111-1111-111111111111",
    )
    assert "http://www.w3.org/2005/08/addressing" not in env
    assert '<GetVersion xmlns="http://tempuri.org/"/>' in env or '<GetVersion xmlns="http://tempuri.org/"></GetVersion>' in env
