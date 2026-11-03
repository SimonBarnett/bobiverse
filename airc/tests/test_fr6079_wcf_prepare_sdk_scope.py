"""FR #6079: denylist generic FORMPREP; EFORM uses SDK SOAP + exact ENAME."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import priority_wcf as wcf

SDK_INDEX = (
    Path(__file__).resolve().parents[1]
    / "priority-worker"
    / "sdk"
    / "priority-web-sdk"
    / "index.js"
)


def _pw() -> str:
    return "FAKE_" + "PREP" + "79"


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


def test_fr6079_sdk_index_lists_every_prepare_op():
    text = SDK_INDEX.read_text(encoding="utf-8")
    missing = [op for op in wcf.PREPARE_SDK_OPS if op not in text]
    assert missing == []
    assert "FormSetSearchFilterMob" not in text
    assert "GetRowsMob" not in text
    assert "FormSetActiveRowMob" not in text
    assert "FormEndMob" not in text


def test_fr6079_generic_procstart_formprep_refused_no_soap():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    for line in (
        "PRIORITY wcf ProcStart type=P ename=FORMPREP "
        "url=https://priority.example.invalid user=tabula",
        "PRIORITY wcf ProcStartActivate type=P ename=FORMPREPDRCT2 "
        "url=https://priority.example.invalid user=tabula",
        "PRIORITY wcf ProcStartMob type=P ename=REPPREP "
        "url=https://priority.example.invalid user=tabula",
        "PRIORITY wcf ProcStart type=P ename=PROCPREP "
        "url=https://priority.example.invalid user=tabula",
    ):
        seen.clear()
        out = wcf.run_priority_wcf(
            line,
            passed_password=_pw(),
            http_post=fake_post,
            mode="direct",
        )
        assert out.get("ok") is False
        assert out.get("error") == "use_prepare_verb"
        assert seen == []


def test_fr6079_job_id_required_before_soap():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "job_id_required"
    assert seen == []


def test_fr6079_ename_mismatch_one_wrong_row():
    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        if act == "FormStartMob":
            return 400, _result(act, {"ok": True, "statexml": "SX-START"})
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(
                act,
                {
                    "statexml": "SX-Q",
                    "RowsData": {"EFORM": {"1": {"ENAME": "OTHERFORM"}}},
                },
            )
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "ename_mismatch"


def test_fr6079_prepare_uses_sdk_ops_and_statexml():
    actions: list[str] = []
    stage = {"q": 0}

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, {"ok": True, "statexml": "SX1"})
        if act == "FormQueryDlgExecuteMob":
            stage["q"] += 1
            assert "SX" in blob
            filt = base64.b64encode(
                json.dumps({"ENAME": "WWWSHOWCUST"}).encode("utf-8")
            ).decode("ascii")
            assert filt in blob
            if stage["q"] == 1:
                return 400, _result(
                    act,
                    {
                        "statexml": "SX2",
                        "RowsData": {"EFORM": {"1": {"ENAME": "WWWSHOWCUST"}}},
                    },
                )
            return 400, _result(
                act,
                {
                    "statexml": "SXE",
                    "RowsData": {"FORMPREPERRS": {"1": {"ENAME": "WWWSHOWCUST"}}},
                },
            )
        if act == "FormJumpLineMob":
            assert "SX2" in blob
            assert "<line>1</line>" in blob
            return 400, _result(act, {"statexml": "SX3"})
        if act == "FormActivateMob":
            assert "SX3" in blob
            assert "FORMPREPDRCT2" not in blob
            assert "<before>" in blob
            return 400, _result(
                act,
                {
                    "statexml": "SX4",
                    "Activate": [{"table": "EFORM", "link": "ENAME", "linkid": "L79"}],
                },
            )
        if act == "ProcStartActivateMob":
            assert "L79" in blob
            assert "FORMPREPDRCT2" in blob
            return 400, _result(act, {"session": "S79", "type": "end", "message": "ok"})
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is True
    assert out.get("ename") == "WWWSHOWCUST"
    assert "FormSetSearchFilterMob" not in actions
    assert "GetRowsMob" not in actions
    assert "FormSetActiveRowMob" not in actions
    assert "FormEndMob" not in actions
    assert actions[:4] == [
        "FormStartMob",
        "FormQueryDlgExecuteMob",
        "FormJumpLineMob",
        "FormActivateMob",
    ]
    invented = set(actions) - wcf.PREPARE_SDK_OPS
    assert not invented
    sdk = SDK_INDEX.read_text(encoding="utf-8")
    for op in actions:
        assert op in sdk


def test_fr6079_step_limit_kills():
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, {"statexml": "S"})
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(
                act,
                {"RowsData": {"EFORM": {"1": {"ENAME": "WWWSHOWCUST"}}}},
            )
        if act == "FormJumpLineMob":
            return 400, _result(act, {"statexml": "S"})
        if act == "FormActivateMob":
            return 400, _result(
                act,
                {"Activate": [{"table": "EFORM", "link": "ENAME", "linkid": "L"}]},
            )
        if act == "ProcStartActivateMob":
            return 400, _result(act, {"session": "SK", "type": "message"})
        if act == "ProcContinueMob":
            return 400, _result(act, {"session": "SK", "type": "message"})
        if act == "ProcKillProcessMob":
            return 400, _result(act, {"ok": True})
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "step_limit"
    assert "ProcKillProcessMob" in actions
