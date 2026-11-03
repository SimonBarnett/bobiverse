"""FR #6047: UsernameToken user\\ttabulaini + PriorityNS headers before Security."""
from __future__ import annotations

from datetime import datetime, timezone

import priority_wcf as wcf


def _secret() -> str:
    return "FAKE_" + "WCF" + "NS" + "47"


def _appkey() -> str:
    return "FAKE_" + "APP" + "KEY" + "47"


def test_fr6047_format_username_tab_and_ini():
    assert wcf.format_wcf_username("tabula") == "tabula\ttabula.ini"
    assert wcf.format_wcf_username("tabula", tabulaini="custom.ini") == "tabula\tcustom.ini"
    assert (
        wcf.format_wcf_username("tabula", tabulaini="tabula.ini", auth_audience="aud1")
        == "tabula\ttabula.ini\taud1"
    )


def test_fr6047_golden_envelope_username_and_priorityns_order():
    secret = _secret()
    now = datetime(2026, 11, 3, 8, 0, 0, tzinfo=timezone.utc)
    env = wcf.build_envelope(
        "GetVersion",
        user=wcf.format_wcf_username("tabula"),
        password=secret,
        now=now,
        token_id="uuid-test-1",
        hostname="FLAMINGO",
        company="live1",
        utc_offset="0",
        language=3,
        other_info="app_airc,",
    )
    assert "tabula\ttabula.ini" in env
    header = env.split("<s:Body>", 1)[0]
    assert header.find("<Language") < header.find("<Hostname")
    assert header.find("<Hostname") < header.find("<WinUser")
    assert header.find("<WinUser") < header.find("<UtcOffset")
    assert header.find("<UtcOffset") < header.find("<Environment")
    assert header.find("<Environment") < header.find("<SilverLight")
    assert header.find("<SilverLight") < header.find("<OtherInfo")
    assert header.find("<OtherInfo") < header.find("<o:Security")
    assert 'xmlns="PriorityNS"' in env
    assert "<Language xmlns=\"PriorityNS\">3</Language>" in env
    assert "<Hostname xmlns=\"PriorityNS\">FLAMINGO</Hostname>" in env
    assert "<WinUser xmlns=\"PriorityNS\"></WinUser>" in env
    assert "<Environment xmlns=\"PriorityNS\">live1</Environment>" in env
    assert "<SilverLight xmlns=\"PriorityNS\">2</SilverLight>" in env
    assert "<OtherInfo xmlns=\"PriorityNS\">app_airc,</OtherInfo>" in env
    assert secret not in wcf.redact(env, secret)


def test_fr6047_invalid_security_still_wcf_security_rejected():
    fault = (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>a:InvalidSecurity</faultcode>"
        "<faultstring>An error occurred when verifying security for the message.</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )
    parsed = wcf.parse_soap_response(fault)
    assert parsed["error"] == wcf.WCF_SECURITY_REJECTED


def test_fr6047_allowlist_ignores_irc_tabulaini_company_user():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(data.decode("utf-8", errors="replace"))
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>ok</s:Body></s:Envelope>'
        )

    class _Allow:
        def get(self, ident):
            if ident != "hrs-dev-live1":
                return None
            return type(
                "I",
                (),
                {
                    "public_dict": lambda self: {
                        "url": "https://priority.example.invalid",
                        "user": "tabula",
                        "company": "live1",
                        "tabulaIni": "tabula.ini",
                        "credentialTarget": "PriorityWeb/hrs-dev-live1",
                    }
                },
            )()

    out = wcf.run_priority_wcf(
        "PRIORITY wcf GetVersion hrs-dev-live1 user=evil tabulaini=hack.ini company=OTHER",
        allowlist=_Allow(),
        passed_password=_secret(),
        http_post=fake_post,
        mode="relay",
    )
    assert out.get("ok") is True
    blob = seen[0]
    assert "tabula\ttabula.ini" in blob
    assert "evil" not in blob
    assert "hack.ini" not in blob
    assert "<Environment xmlns=\"PriorityNS\">live1</Environment>" in blob
    assert "OTHER" not in blob


def test_fr6047_redact_covers_appkey_and_client_uses_instance():
    secret = _secret()
    key = _appkey()
    red = wcf.redact(f"other=appkey_{key}, password={secret}", secret, extra=key)
    assert secret not in red
    assert key not in red

    captured = []

    def fake_post(url, data, headers, timeout_s=30.0):
        captured.append(data.decode("utf-8", errors="replace"))
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>21</s:Body></s:Envelope>'
        )

    def fetch(target):
        if "AppKey" in target:
            return key
        return secret

    out = wcf.PriorityWcfClient(
        {
            "url": "https://priority.example.invalid",
            "user": "tabula",
            "company": "live1",
            "hostname": "FLAMINGO",
            "credentialTarget": "PriorityWeb/x",
            "wcfAppId": "aid1",
            "wcfAppKeyTarget": "PriorityWeb/AppKey",
        },
        cred_fetcher=fetch,
        http_post=fake_post,
    ).get_version()
    assert out["ok"] is True
    assert "tabula\ttabula.ini" in captured[0]
    assert f"appid_aid1," in captured[0]
    assert f"appkey_{key}," in captured[0]
    assert key not in str(out)
    assert secret not in str(out)
