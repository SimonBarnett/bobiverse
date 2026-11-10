"""FR #6058: HTTP 400 + <Op>Result is success; decode Mob results compactly."""
from __future__ import annotations

import base64
import json

import airc_priority as ap
import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "HTTP" + "58"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _result_envelope(op: str, result_text: str) -> str:
    return (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
        f'<{op}Response xmlns="{wcf.TEMPURI}">'
        f"<{op}Result>{result_text}</{op}Result>"
        f"</{op}Response></s:Body></s:Envelope>"
    )


def test_fr6058_http_400_with_result_is_ok():
    version = "3.0.228.7321"
    xml = _result_envelope("GetFileVersion", _b64(version))
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, xml),
    ).get_version()
    assert out["ok"] is True
    assert out.get("http_status") == 400
    assert out.get("error") != wcf.WCF_HTTP_ERROR
    assert out.get("version") == version
    assert _pw() not in str(out)


def test_fr6058_http_400_fault_still_fails():
    fault = (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>s:MustUnderstand</faultcode>"
        "<faultstring>Action not understood</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, fault),
    ).get_version()
    assert out["ok"] is False
    assert out["error"] == wcf.SOAP_FAULT
    assert out.get("http_status") == 400


def test_fr6058_http_400_empty_or_bad_xml_fails():
    inst = {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"}
    empty = wcf.PriorityWcfClient(
        inst, passed_password=_pw(), http_post=lambda *a, **k: (400, "")
    ).get_version()
    assert empty["ok"] is False
    assert empty["error"] == wcf.WCF_HTTP_ERROR
    assert empty.get("http_status") == 400
    junk = wcf.PriorityWcfClient(
        inst, passed_password=_pw(), http_post=lambda *a, **k: (400, "<not-soap")
    ).get_version()
    assert junk["ok"] is False
    assert junk["error"] == wcf.WCF_HTTP_ERROR
    no_result = wcf.PriorityWcfClient(
        inst,
        passed_password=_pw(),
        http_post=lambda *a, **k: (
            400,
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body/></s:Envelope>',
        ),
    ).get_version()
    assert no_result["ok"] is False


def test_fr6058_companies_compact_under_irc_cap():
    names = [f"co{i:02d}" for i in range(21)]
    names[1] = "live1"
    payload = [{"DNAME": n, "DBNAME": n + "db", "TITLE": n + " title"} for n in names]
    xml = _result_envelope("GeneralCompaniesMob", _b64(json.dumps(payload)))
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, xml),
    ).general_companies()
    assert out["ok"] is True
    assert out.get("count") == 21
    assert "live1" in (out.get("companies") or [])
    assert "DBNAME" not in json.dumps(out.get("companies"))
    framed, code = ap.format_bounded_priority_out("aabb6058", out, 0)
    assert code == 0
    assert len(framed.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(framed.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert body.get("error") != "reply-too-large"
    assert "live1" in (body.get("companies") or [])
