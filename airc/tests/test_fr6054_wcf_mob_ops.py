"""FR #6054: WCF wire ops are *Mob / GetFileVersion; old names are aliases."""
from __future__ import annotations

import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "MOB" + "54"


def test_fr6054_aliases_resolve_to_sdk_ops():
    assert wcf.resolve_wcf_op("GetVersion") == "GetFileVersion"
    assert wcf.resolve_wcf_op("GetFileVersion") == "GetFileVersion"
    assert wcf.resolve_wcf_op("GeneralCompanies") == "GeneralCompaniesMob"
    assert wcf.resolve_wcf_op("GeneralCompaniesMob") == "GeneralCompaniesMob"
    assert wcf.resolve_wcf_op("ProcStart") == "ProcStartMob"
    assert wcf.resolve_wcf_op("ProcContinue") == "ProcContinueMob"
    assert wcf.resolve_wcf_op("ProcEnd") == "ProcEndMob"
    assert wcf.resolve_wcf_op("ProcStartMob") == "ProcStartMob"
    assert wcf.resolve_wcf_op("not-an-op") is None


def test_fr6054_client_sends_mob_soapaction_and_empty_company_body():
    secret = _pw()
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append((data.decode("utf-8"), headers))
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
            f'<GeneralCompaniesMobResponse xmlns="{wcf.TEMPURI}">'
            "<GeneralCompaniesMobResult>dname=live1</GeneralCompaniesMobResult>"
            "</GeneralCompaniesMobResponse></s:Body></s:Envelope>"
        )

    c = wcf.PriorityWcfClient(
        {
            "url": "https://priority.example.invalid",
            "user": "tabula",
            "company": "live1",
            "hostname": "FLAMINGO",
        },
        passed_password=secret,
        http_post=fake_post,
    )
    out = c.general_companies()
    assert out["ok"] is True
    assert "dname=live1" in (out.get("body") or "")
    env, hdr = seen[0]
    assert hdr["SOAPAction"] == '"http://tempuri.org/IWCFService/GeneralCompaniesMob"'
    assert '<GeneralCompaniesMob xmlns="http://tempuri.org/"/>' in env or (
        '<GeneralCompaniesMob xmlns="http://tempuri.org/"></GeneralCompaniesMob>' in env
    )
    assert "GeneralCompanies>" not in env
    assert secret not in str(out)
    assert secret not in (out.get("raw") or "")


def test_fr6054_getversion_alias_is_getfileversion():
    secret = _pw()
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append((data.decode("utf-8"), headers))
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
            f'<GetFileVersionResponse xmlns="{wcf.TEMPURI}">'
            "<GetFileVersionResult>21.1</GetFileVersionResult>"
            "</GetFileVersionResponse></s:Body></s:Envelope>"
        )

    c = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula"},
        passed_password=secret,
        http_post=fake_post,
    )
    out = c.get_version()
    assert out["ok"] is True
    assert "21.1" in (out.get("body") or "")
    env, hdr = seen[0]
    assert hdr["SOAPAction"] == '"http://tempuri.org/IWCFService/GetFileVersion"'
    assert "GetFileVersion" in env
    assert "<GetVersion " not in env and "<GetVersion/" not in env


def test_fr6054_proc_aliases_and_irc_parse():
    secret = _pw()
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(headers["SOAPAction"])
        return 200, f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>ok</s:Body></s:Envelope>'

    c = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula"},
        passed_password=secret,
        http_post=fake_post,
    )
    c.proc_start(typ="P", ename="FORMPREP")
    c.proc_continue("SESS1")
    c.proc_end("SESS1")
    assert seen == [
        '"http://tempuri.org/IWCFService/ProcStartMob"',
        '"http://tempuri.org/IWCFService/ProcContinueMob"',
        '"http://tempuri.org/IWCFService/ProcEndMob"',
    ]
    p = wcf.parse_priority_wcf_command("PRIORITY wcf GeneralCompanies hrs-dev-live1")
    assert p["op"] == "GeneralCompaniesMob"
    p2 = wcf.parse_priority_wcf_command("PRIORITY wcf GetFileVersion hrs-dev-live1")
    assert p2["op"] == "GetFileVersion"
    p3 = wcf.parse_priority_wcf_command("PRIORITY wcf GetVersion hrs-dev-live1")
    assert p3["op"] == "GetFileVersion"
