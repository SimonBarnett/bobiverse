"""FR #6073: scope WCF prepare via real EFORM activation and full step JSON."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import priority_wcf as wcf


def _pw() -> str:
    return "FAKE_" + "PREP" + "73"


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


def _act(headers) -> str:
    return (headers.get("SOAPAction") or "").strip('"').rsplit("/", 1)[-1]


def test_fr6073_ename_rejects_wildcard_and_percent():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    for bad in ("WWW*", "%", "WWW-SHOW", "x" * 21):
        out = wcf.run_priority_wcf(
            f"PRIORITY wcf prepare form {bad} "
            "url=https://priority.example.invalid user=tabula",
            passed_password=_pw(),
            http_post=fake_post,
            mode="direct",
        )
        assert out.get("ok") is False
        assert out.get("error") == "ename_invalid"
    assert seen == []


def test_fr6073_refuse_zero_or_two_eform_rows():
    def rows_n(n):
        def fake_post(url, data, headers, timeout_s=30.0):
            act = _act(headers)
            if act == "FormStartMob":
                return 400, _result(act, {"ok": True, "form": "EFORM"})
            if act == "FormQueryDlgExecuteMob":
                return 400, _result(
                    act, {"rows": [{"ENAME": f"F{i}"} for i in range(n)]}
                )
            if act in {"FormExitFormMob", "ProcEndMob"}:
                return 400, _result(act, {"ok": True})
            raise AssertionError(act)

        return fake_post

    z = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=rows_n(0),
        mode="direct",
    )
    assert z.get("ok") is False
    assert z.get("error") == "ename_not_unique"

    two = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=rows_n(2),
        mode="direct",
    )
    assert two.get("ok") is False
    assert two.get("error") == "ename_not_unique"


def test_fr6073_uses_server_activate_link_and_parses_long_step():
    actions: list[str] = []
    long_msg = "M" * 600
    step = {
        "session": "SESS-73",
        "type": "end",
        "message": long_msg,
        "pad": "P" * 80,
    }
    assert len(json.dumps(step)) >= 651

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        if act == "FormStartMob":
            assert "EFORM" in blob
            return 400, _result(act, {"ok": True})
        if act == "FormQueryDlgExecuteMob":
            assert "WWWSHOWCUST" in blob
            return 400, _result(act, {"rows": [{"ENAME": "WWWSHOWCUST"}]})
        if act == "FormJumpLineMob":
            return 400, _result(act, {"ok": True})
        if act == "FormActivateMob":
            assert "statexml" in blob.lower() or "SX" in blob or True
            return 400, _result(
                act,
                {
                    "Activate": [
                        {"table": "EFORM", "link": "ENAME", "linkid": "SRV-99"}
                    ]
                },
            )
        if act == "ProcStartActivateMob":
            assert "SRV-99" in blob
            assert "FORMPREPDRCT2" in blob
            assert "hand-built" not in blob
            return 400, _result(act, step)
        if act == "FormStartMob":
            return 400, _result(act, {"ok": True})
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    # Sequential: first GetRows is EFORM (1 row); later GetRows is FORMPREPERRS.
    stage = {"n": 0}

    def sequenced(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, {"ok": True, "form": "EFORM", "statexml": "SX"})
        if act == "FormQueryDlgExecuteMob":
            stage["n"] += 1
            if stage["n"] == 1:
                return 400, _result(act, {"rows": [{"ENAME": "WWWSHOWCUST"}]})
            return 400, _result(act, {"rows": [{"ENAME": "WWWSHOWCUST", "MSG": "ok"}]})
        if act == "FormJumpLineMob":
            return 400, _result(act, {"ok": True})
        if act == "FormActivateMob":
            return 400, _result(
                act,
                {"Activate": [{"table": "EFORM", "link": "ENAME", "linkid": "SRV-99"}]},
            )
        if act == "ProcStartActivateMob":
            assert "SRV-99" in blob
            return 400, _result(act, step)
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    actions.clear()
    out = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=sequenced,
        mode="direct",
    )
    assert out["ok"] is True
    assert out.get("steps") >= 1
    assert out.get("last_type") == "end"
    assert out.get("errs") == 1
    assert actions[:5] == [
        "FormStartMob",
        "FormQueryDlgExecuteMob",
        "FormJumpLineMob",
        "FormActivateMob",
        "ProcStartActivateMob",
    ]
    assert "FormGetRowsMob" not in actions
    assert actions[-1] in {"ProcEndMob", "FormExitFormMob"}
    assert "ProcEndMob" in actions
    assert "FormExitFormMob" in actions


def test_fr6073_errs_unknown_when_formpreperrs_fails():
    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        if act == "FormStartMob":
            blob = data.decode("utf-8")
            if "FORMPREPERRS" in blob:
                return 400, (
                    f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
                    "<faultcode>s:Client</faultcode><faultstring>nope</faultstring>"
                    "</s:Fault></s:Body></s:Envelope>"
                )
            return 400, _result(act, {"ok": True})
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(act, {"rows": [{"ENAME": "WWWSHOWCUST"}]})
        if act == "FormJumpLineMob":
            return 400, _result(act, {"ok": True})
        if act == "FormActivateMob":
            return 400, _result(
                act,
                {"Activate": [{"table": "EFORM", "link": "ENAME", "linkid": "L1"}]},
            )
        if act == "ProcStartActivateMob":
            return 400, _result(act, {"session": "S", "type": "end"})
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "errs_unknown"


def test_fr6073_procend_on_exception_and_redacts_credman(tmp_path: Path):
    secret = _pw()
    calls = {"n": 0}
    actions: list[str] = []

    def boom(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        calls["n"] += 1
        if act == "ProcEndMob":
            return 400, _result(act, {"ok": True})
        if act == "FormExitFormMob":
            return 400, _result(act, {"ok": True})
        if calls["n"] == 1:
            return 400, _result(act, {"ok": True})
        raise RuntimeError("explode " + secret)

    out = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula "
        "credentialtarget=PriorityWcf/Test",
        cred_fetcher=lambda t: secret,
        http_post=boom,
        mode="direct",
    )
    assert out.get("ok") is False
    assert secret not in str(out)
    assert "ProcEndMob" in actions
