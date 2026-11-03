"""FR #6049: WCF result redaction must apply secrets cumulatively."""
from __future__ import annotations

import priority_wcf as wcf


def _pw() -> str:
    return "PH-" + "pw-" + "Zq81"


def _key() -> str:
    return "PH-" + "ak-" + "Km22"


def _fault(msg: str) -> str:
    return (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
        "<faultcode>s:Client</faultcode>"
        f"<faultstring>{msg}</faultstring>"
        "</s:Fault></s:Body></s:Envelope>"
    )


def _client(*, password: str, app_key: str = "", fault_msg: str):
    def fetch(target):
        if "AppKey" in target:
            return app_key
        return password

    inst = {
        "url": "https://priority.example.invalid",
        "user": "tabula",
        "company": "live1",
        "credentialTarget": "PriorityWeb/x",
    }
    if app_key:
        inst["wcfAppKeyTarget"] = "PriorityWeb/AppKey"
    return wcf.PriorityWcfClient(
        inst,
        cred_fetcher=fetch,
        http_post=lambda *a, **k: (500, _fault(fault_msg)),
    )


def test_fr6049_fault_redacts_password_and_appkey_together():
    pw, key = _pw(), _key()
    user_tok = wcf.format_wcf_username("tabula")
    msg = f"bad {pw} {key} {user_tok}"
    out = _client(password=pw, app_key=key, fault_msg=msg).get_version()
    blob = str(out)
    assert pw not in blob
    assert key not in blob
    assert pw not in (out.get("fault_string") or "")
    assert key not in (out.get("fault_string") or "")
    assert "***" in (out.get("fault_string") or "")


def test_fr6049_fault_redacts_password_when_no_appkey():
    pw = _pw()
    out = _client(password=pw, fault_msg=f"bad {pw} only").get_version()
    assert pw not in str(out)
    assert pw not in (out.get("fault_string") or "")


def test_fr6049_redact_all_is_cumulative():
    pw, key = _pw(), _key()
    got = wcf.redact_all(f"bad {pw} {key}", pw, key)
    assert pw not in got
    assert key not in got
    assert got.count("***") >= 2
