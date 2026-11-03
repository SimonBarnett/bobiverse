"""FR #6073: scope WCF prepare via real EFORM activation and full step JSON."""
from __future__ import annotations

import json
from pathlib import Path

import priority_wcf as wcf
import test_fr6079_wcf_prepare_sdk_scope as fx


def _pw() -> str:
    return "FAKE_" + "PREP" + "73"


def test_fr6073_ename_rejects_wildcard_and_percent():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(fx._act(headers))
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
    def rows_of(lines: list[tuple[int, dict[str, str]]]):
        def fake_post(url, data, headers, timeout_s=30.0):
            act = fx._act(headers)
            if act == "FormStartMob":
                return 400, fx._result(act, fx._eform_start())
            if act == "FormQueryDlgExecuteMob":
                return 400, fx._result(act, fx._eform_rows(lines))
            if act in {"FormExitFormMob", "ProcEndMob"}:
                return 400, fx._result(act, {"Form": [{"ok": True}]})
            raise AssertionError(act)

        return fake_post

    z = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=rows_of([]),
        mode="direct",
    )
    assert z.get("ok") is False
    assert z.get("error") == "ename_not_unique"

    # Two live rows, even when both ENAMEs match, must not activate.
    two = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=rows_of(
            [
                (1, {"ENAME": "WWWSHOWCUST"}),
                (2, {"ENAME": "WWWSHOWCUST"}),
            ]
        ),
        mode="direct",
    )
    assert two.get("ok") is False
    assert two.get("error") == "ename_not_unique"


def test_fr6073_uses_server_activate_link_and_parses_long_step():
    actions: list[str] = []
    blobs: list[str] = []
    long_msg = "M" * 600
    step = fx._proc_doc("SESS-73", "", finished=1, message=long_msg)
    assert len(json.dumps(step)) >= 651
    stage = {"q": 0, "start": 0}

    def sequenced(url, data, headers, timeout_s=30.0):
        act = fx._act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        blobs.append(blob)
        if act == "FormStartMob":
            stage["start"] += 1
            if "FORMPREPERRS" in blob:
                assert "<autoRetrieveFirstRows>true</autoRetrieveFirstRows>" in blob
                return 400, fx._result(
                    act, fx._form_doc("FORMPREPERRS", fx.ERR_TABLE, "E0", fx.ERR_COLS, [])
                )
            assert "<form>EFORM</form>" in blob
            assert "<autoRetrieveFirstRows>false</autoRetrieveFirstRows>" in blob
            return 400, fx._result(act, fx._eform_start("S0"))
        if act == "FormQueryDlgExecuteMob":
            stage["q"] += 1
            assert "<ic>true</ic>" in blob
            assert "<queryname></queryname>" in blob
            if stage["q"] == 1:
                assert wcf.sdk_statexml("S0", 0, 1, "") in blob
                return 400, fx._result(
                    act, fx._eform_rows([(1, {"ENAME": "WWWSHOWCUST"})], "S1")
                )
            assert wcf._filter_xml(fx.ERR_COLS[0]["field"], "WWWSHOWCUST") in blob
            return 400, fx._result(
                act,
                fx._form_doc(
                    "FORMPREPERRS",
                    fx.ERR_TABLE,
                    "E1",
                    fx.ERR_COLS,
                    [(1, {"ENAME": "WWWSHOWCUST", "MESSAGE": "ok"})],
                    include_table=False,
                    position_field=2,
                ),
            )
        if act == "FormJumpLineMob":
            # FV line 1 and Position.line 1 → display index 1. Value is the ENAME cell.
            assert wcf.sdk_statexml("S1", fx.ENAME_FIELD, 1, "WWWSHOWCUST") in blob
            assert "<line>1</line>" in blob
            return 400, fx._result(
                act,
                fx._form_doc(
                    "EFORM",
                    fx.EFORM_TABLE,
                    "S2",
                    fx.EFORM_COLS,
                    [],
                    include_table=False,
                    position_field=fx.ENAME_FIELD,
                    position_line=1,
                ),
            )
        if act == "FormActivateMob":
            expected = wcf.sdk_statexml("S2", fx.ENAME_FIELD, 1, "")
            assert expected in blob
            assert "<before>true</before>" in blob
            assert "FORMPREPDRCT2" not in blob
            return 400, fx._result(
                act,
                fx._form_doc(
                    "EFORM",
                    fx.EFORM_TABLE,
                    "S3",
                    fx.EFORM_COLS,
                    [],
                    include_table=False,
                    activate={"table": "EFORM", "link": "ENAME", "linkid": "SRV-99"},
                ),
            )
        if act == "ProcStartActivateMob":
            assert "SRV-99" in blob
            assert "FORMPREPDRCT2" in blob
            assert "<table>EFORM</table>" in blob
            assert "<link>ENAME</link>" in blob
            assert "<avoidmessages>false</avoidmessages>" in blob
            assert "hand-built" not in blob
            return 400, fx._result(act, step)
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, fx._result(act, {"Form": [{"Position": [{"session": "Z"}]}]})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6073 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=sequenced,
        mode="direct",
    )
    assert out["ok"] is False, out
    assert out.get("error") == "prepare_errors"
    assert out.get("steps") >= 1
    assert out.get("last_type") == "end"
    assert out.get("last_message") == long_msg[:80]
    assert out.get("errs") == 1
    assert out.get("rows") == [{"ENAME": "WWWSHOWCUST", "MESSAGE": "ok"}]
    assert actions[:5] == [
        "FormStartMob",
        "FormQueryDlgExecuteMob",
        "FormJumpLineMob",
        "FormActivateMob",
        "ProcStartActivateMob",
    ]
    assert "FormGetRowsMob" not in actions
    assert "ProcEndMob" in actions
    assert "FormExitFormMob" in actions
    exit_blobs = [b for a, b in zip(actions, blobs) if a == "FormExitFormMob"]
    assert any(wcf.sdk_statexml("E1", 2, 1, "WWWSHOWCUST") in b for b in exit_blobs)


def test_fr6073_errs_unknown_when_formpreperrs_fails():
    stage = {"start": 0}

    def fake_post(url, data, headers, timeout_s=30.0):
        act = fx._act(headers)
        blob = data.decode("utf-8")
        if act == "FormStartMob":
            stage["start"] += 1
            if "FORMPREPERRS" in blob:
                return 400, (
                    f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body><s:Fault>'
                    "<faultcode>s:Client</faultcode><faultstring>nope</faultstring>"
                    "</s:Fault></s:Body></s:Envelope>"
                )
            return 400, fx._result(act, fx._eform_start())
        if act == "FormQueryDlgExecuteMob":
            return 400, fx._result(act, fx._eform_rows([(1, {"ENAME": "WWWSHOWCUST"})]))
        if act == "FormJumpLineMob":
            return 400, fx._result(
                act,
                fx._form_doc(
                    "EFORM",
                    fx.EFORM_TABLE,
                    "S2",
                    fx.EFORM_COLS,
                    [],
                    include_table=False,
                ),
            )
        if act == "FormActivateMob":
            return 400, fx._result(
                act,
                fx._form_doc(
                    "EFORM",
                    fx.EFORM_TABLE,
                    "S3",
                    fx.EFORM_COLS,
                    [],
                    include_table=False,
                    activate={"table": "EFORM", "link": "ENAME", "linkid": "L1"},
                ),
            )
        if act == "ProcStartActivateMob":
            return 400, fx._result(act, fx._proc_doc("S", "", finished=1))
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, fx._result(act, {"Form": [{"ok": True}]})
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
    assert out.get("errs") is None


def test_fr6073_procend_on_exception_and_redacts_credman(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    secret = _pw()
    actions: list[str] = []

    def boom(url, data, headers, timeout_s=30.0):
        act = fx._act(headers)
        actions.append(act)
        if act in {"ProcEndMob", "FormExitFormMob"}:
            return 400, fx._result(act, {"Form": [{"ok": True}]})
        if act == "FormStartMob":
            return 400, fx._result(act, fx._eform_start())
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
    assert "ProcEndMob" not in actions
    assert "FormExitFormMob" in actions
    log = tmp_path / "jobs" / "aabb6073" / "wcf-prepare.json"
    assert log.is_file()
    assert secret not in log.read_text(encoding="utf-8")
