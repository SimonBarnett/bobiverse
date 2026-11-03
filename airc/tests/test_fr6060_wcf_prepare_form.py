"""FR #6060: native WCF PRIORITY wcf prepare form (no WINRUN / node SDK)."""
from __future__ import annotations

import base64
import json

import airc_priority as ap
import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "PREP" + "60"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _result(op: str, obj: dict) -> str:
    payload = _b64(json.dumps(obj))
    return (
        f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
        f'<{op}Response xmlns="{wcf.TEMPURI}">'
        f"<{op}Result>{payload}</{op}Result>"
        f"</{op}Response></s:Body></s:Envelope>"
    )


def test_fr6060_refuse_without_ename():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(headers.get("SOAPAction"))
        return 400, ""

    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "ename_missing"
    assert seen == []
    assert _pw() not in str(out)


def test_fr6060_full_sequence_and_formpreperrs_and_procend():
    secret = _pw()
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = (headers.get("SOAPAction") or "").strip('"').rsplit("/", 1)[-1]
        blob = data.decode("utf-8")
        actions.append(act)
        assert secret in blob
        assert "http://www.w3.org/2005/08/addressing" not in blob
        if act == "ProcStartActivateMob":
            assert "FORMPREPDRCT2" in blob
            assert "EFORM" in blob
            assert "WWWSHOWCUST" in blob
            assert "WINACTIV" not in blob
            return 400, _result(
                act,
                {
                    "session": "SESS-60",
                    "type": "inputFields",
                    "input": {
                        "EditField": [
                            {"field": "P1", "title": "Form name", "value": ""},
                            {"field": "P2", "title": "Other", "value": "keep"},
                        ]
                    },
                },
            )
        if act == "ProcEditFieldsOKMob":
            assert "WWWSHOWCUST" in blob
            assert "SESS-60" in blob
            return 400, _result(act, {"session": "SESS-60", "type": "warning", "message": "sure?"})
        if act == "ProcWarningOKMob":
            return 400, _result(act, {"session": "SESS-60", "type": "message", "message": "prep ok"})
        if act == "ProcContinueMob":
            return 400, _result(act, {"session": "SESS-60", "type": "end"})
        if act == "FormGetRowsMob":
            assert "FORMPREPERRS" in blob
            assert "WWWSHOWCUST" in blob
            return 400, _result(
                act,
                {"rows": [{"ENAME": "WWWSHOWCUST", "MSG": "compiled"}]},
            )
        if act == "ProcEndMob":
            assert "SESS-60" in blob
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula company=live1",
        passed_password=secret,
        http_post=fake_post,
        mode="direct",
    )
    assert out["ok"] is True
    assert out.get("ename") == "WWWSHOWCUST"
    assert out.get("steps") >= 3
    assert out.get("last_type") == "end"
    assert out.get("errs") == 1
    assert "ProcStartActivateMob" in actions
    assert "ProcEndMob" in actions
    assert actions[-1] == "ProcEndMob"
    assert "ProcStartMob" not in actions
    assert secret not in str(out)
    framed, code = ap.format_bounded_priority_out("aabb6060", out, 0)
    assert code == 0
    assert len(framed.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(framed.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert body.get("ename") == "WWWSHOWCUST"
    assert body.get("error") != "reply-too-large"


def test_fr6060_procend_on_unknown_step_and_start_fail():
    actions: list[str] = []

    def fail_start(url, data, headers, timeout_s=30.0):
        act = (headers.get("SOAPAction") or "").strip('"').rsplit("/", 1)[-1]
        actions.append(act)
        if act == "ProcStartActivateMob":
            return 400, (
                f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
                "<faultcode>s:Client</faultcode><faultstring>nope</faultstring>"
                "</s:Fault></s:Body></s:Envelope>"
            )
        if act == "ProcEndMob":
            return 400, _result(act, {})
        return 400, ""

    bad = wcf.run_priority_wcf(
        "id=aabb6061 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fail_start,
        mode="direct",
    )
    assert bad["ok"] is False
    assert "ProcEndMob" in actions

    seq = {"n": 0}

    def unknown_then_end(url, data, headers, timeout_s=30.0):
        act = (headers.get("SOAPAction") or "").strip('"').rsplit("/", 1)[-1]
        actions.append(act)
        if act == "ProcStartActivateMob":
            return 400, _result(act, {"session": "S2", "type": "weirdStep"})
        if act == "ProcEndMob":
            seq["n"] += 1
            return 400, _result(act, {})
        return 400, _result(act, {"session": "S2", "type": "end"})

    unk = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form ONLYME "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=unknown_then_end,
        mode="direct",
    )
    assert unk["ok"] is False
    assert unk.get("error") == "unknown_step"
    assert actions.count("ProcEndMob") >= 2


def test_fr6060_parse_wcf_prepare_form():
    p = wcf.parse_priority_wcf_command(
        "id=aabb6060 PRIORITY wcf prepare form WWWSHOWCUST hrs-dev-live1"
    )
    assert p is not None
    assert p["kind"] == "prepare_form"
    assert p["ename"] == "WWWSHOWCUST"
    assert p["instance"] == "hrs-dev-live1"
    assert p["job_id"] == "aabb6060"
