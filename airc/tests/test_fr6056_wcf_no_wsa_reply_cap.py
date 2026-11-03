"""FR #6056: no WS-Addressing in envelope; WCF faults survive IRC shrink."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import airc_priority as ap
import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "WSA" + "56"


def test_fr6056_envelope_has_no_addressing_namespace():
    secret = _pw()
    env = wcf.build_envelope(
        "GetFileVersion",
        user=wcf.format_wcf_username("tabula"),
        password=secret,
        now=datetime(2026, 11, 3, 11, 0, 0, tzinfo=timezone.utc),
        token_id="uuid-test-1",
        hostname="FLAMINGO",
        company="live1",
        endpoint="https://priority.example.invalid/wcf/wcf/Service.svc",
        message_id="urn:uuid:11111111-1111-1111-1111-111111111111",
    )
    assert "http://www.w3.org/2005/08/addressing" not in env
    assert "<a:Action" not in env
    assert "<a:To" not in env
    assert "mustUnderstand" in env
    assert env.find('s:mustUnderstand="1"') == env.rfind('s:mustUnderstand="1"')
    assert "<o:Security" in env
    assert secret in env


def test_fr6056_client_keeps_http_soapaction_without_wsa():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append((data.decode("utf-8"), headers))
        return 200, f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>21</s:Body></s:Envelope>'

    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=fake_post,
    ).get_version()
    assert out["ok"] is True
    env, hdr = seen[0]
    assert hdr["SOAPAction"] == '"http://tempuri.org/IWCFService/GetFileVersion"'
    assert "http://www.w3.org/2005/08/addressing" not in env


def test_fr6056_wcf_fault_shrink_keeps_status_and_code():
    payload = {
        "action": "wcf",
        "ok": False,
        "error": "soap_fault",
        "http_status": 400,
        "fault_code": "s:MustUnderstand",
        "fault_string": "The header 'Action' from the namespace was not understood " * 8,
        "raw": "R" * 800,
        "via": "wcf",
        "op": "GetFileVersion",
        "endpoint_ok": True,
    }
    raw_line = "out id=aabb6056 seq=1 " + json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    )
    assert len(raw_line.encode("utf-8")) > ap.PRIORITY_REPLY_MAX_BYTES
    out, exit_code = ap.format_bounded_priority_out("aabb6056", payload, 1)
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    assert exit_code == 1
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("error") == "soap_fault"
    assert body.get("http_status") == 400
    assert body.get("fault_code") == "s:MustUnderstand"
    assert body.get("ok") is False
    assert body.get("error") != "reply-too-large"
    assert "raw" not in body or len(str(body.get("raw") or "")) < 40
