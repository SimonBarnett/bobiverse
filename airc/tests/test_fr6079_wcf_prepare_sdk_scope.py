"""FR #6079: generic prepare denylist; EFORM uses published SDK SOAP shapes."""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import re
import tempfile
from pathlib import Path

import airc_console as ac
import priority_wcf as wcf
from airc_auth_helpers import ops_auth

SDK_INDEX = (
    Path(__file__).resolve().parents[1]
    / "priority-worker"
    / "sdk"
    / "priority-web-sdk"
    / "index.js"
)
SDK_SHA = SDK_INDEX.parent / "index.js.sha256"


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


def _column(name: str, field: int, height: int = 20) -> dict:
    return {"zoomname": name, "field": field, "height": height, "type": 1, "width": 20}


def _fv(table: int, field: int, line: int, value: str) -> dict:
    return {"FV": f"{table}\t{field}\t{line}\t0\t0\t{value}"}


def _form_doc(
    name: str,
    table: int,
    session: str,
    columns: list[dict],
    rows: list[tuple[int, dict[str, str]]],
    *,
    activate: dict | None = None,
    include_table: bool = True,
    position_line: int = 1,
    position_field: int = 0,
) -> dict:
    """SOAP result shape: Form[0].NewTable / RT / Position / Activate."""
    ids = {col["zoomname"]: col["field"] for col in columns}
    rt = []
    for line, vals in rows:
        for col_name, value in vals.items():
            rt.append(_fv(table, ids[col_name], line, value))
    form: dict = {
        "Position": [
            {
                "session": session,
                "table": table,
                "field": position_field,
                "line": position_line,
                "lines": max((line for line, _vals in rows), default=1),
                "curline": position_line,
                "changed": 0,
                "isappend": 0,
            }
        ],
        "RT": rt,
    }
    if include_table:
        form["NewTable"] = [
            {
                "form": 1,
                "table": table,
                "self": 0,
                "title": name,
                "name": name,
                "level": 0,
                "NewColumn": columns,
            }
        ]
    if activate:
        form["Activate"] = [activate]
    return {"Form": [form]}


def _proc_doc(
    session: str,
    step: str = "",
    *,
    finished: int = 0,
    message: str = "",
    messagetype: str = "information",
    extra: dict | None = None,
) -> dict:
    proc: dict = {"session": session, "step": step, "finished": finished}
    if message:
        proc["Message"] = [{"message": message, "messagetype": messagetype}]
    if extra:
        proc.update(extra)
    return {"Procedure": [proc]}


EFORM_TABLE = 10
ERR_TABLE = 11
ENAME_FIELD = 4
EFORM_COLS = [_column("ENAME", ENAME_FIELD, 20), _column("TITLE", 5, 8)]
ERR_COLS = [_column("ENAME", 2, 10), _column("MESSAGE", 3, 10)]


def _eform_start(session: str = "S0") -> dict:
    return _form_doc("EFORM", EFORM_TABLE, session, EFORM_COLS, [])


def _eform_rows(rows: list[tuple[int, dict[str, str]]], session: str = "S1") -> dict:
    return _form_doc(
        "EFORM",
        EFORM_TABLE,
        session,
        EFORM_COLS,
        rows,
        include_table=False,
        position_field=ENAME_FIELD,
    )


def test_fr6079_vendored_index_matches_recorded_sha256():
    text = SDK_INDEX.read_text(encoding="utf-8")
    digest = hashlib.sha256(SDK_INDEX.read_bytes()).hexdigest()
    recorded = SDK_SHA.read_text(encoding="utf-8").split()[0]
    assert digest == recorded
    assert "SOAPAction excerpt" not in text
    verbatim = (
        "$setHeader(this$static, 'SOAPAction', "
        "'http://tempuri.org/IWCFService/FormActivateMob');"
    )
    assert verbatim in text
    # $ToStringData (8099) / $toString_0: ', ' between object pairs, no space in arrays.
    memento = base64.b64decode(wcf.sdk_statexml("S1", 0, 1, "")).decode("utf-8")
    assert memento == (
        '{"Operations":[{"session":"S1"}], "Operation":[{"field":"0", '
        '"line":"1", "curtab":"0", "value":"", "active":"1", "key":"0"}]}'
    )
    lines = text.splitlines()
    for op, line_no in wcf.SDK_BUILDER_LINES.items():
        line = lines[line_no - 1]
        if op in {"ParseRows", "ParseActivate", "ParsePosition"}:
            continue
        assert op in line, (op, line_no, line[:80])
    assert "jo.Form[0].RT" in lines[wcf.SDK_BUILDER_LINES["ParseRows"] - 1]
    assert "Activate" in lines[wcf.SDK_BUILDER_LINES["ParseActivate"] - 1]
    assert "SetPosition" in lines[wcf.SDK_BUILDER_LINES["ParsePosition"] - 1]


def test_fr6079_sdk_index_lists_every_prepare_op():
    text = SDK_INDEX.read_text(encoding="utf-8")
    missing = [op for op in wcf.PREPARE_SDK_OPS if f"IWCFService/{op}" not in text]
    assert missing == []
    src = inspect.getsource(wcf.run_wcf_form_prepare)
    calls = set(re.findall(r'client\.call\(\s*"([A-Za-z0-9]+)"', src))
    assert calls
    assert calls <= wcf.PREPARE_SDK_OPS
    for op in calls:
        assert f"IWCFService/{op}" in text
    assert "FormSetSearchFilterMob" not in text
    assert "GetRowsMob" not in text
    assert "FormSetActiveRowMob" not in text
    assert "FormEndMob" not in text


def test_fr6079_generic_procstart_formprep_refused_no_soap():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    lines = []
    for op in (
        "ProcStart",
        "ProcStartActivate",
        "ProcStartMob",
        "ProcStartActivateMob",
        "ProcNewReport",
        "ProcNewReportMob",
    ):
        for key in ("ename", "name"):
            for prog in (
                "FORMPREP",
                "FORMPREPDRCT",
                "FORMPREPDRCT2",
                "REPPREP",
                "REPPREPDIRECT2",
                "PROCPREP",
            ):
                lines.append(
                    f"PRIORITY wcf {op} type=P {key}={prog} "
                    "url=https://priority.example.invalid user=tabula"
                )
    for line in lines:
        seen.clear()
        out = wcf.run_priority_wcf(
            line,
            passed_password=_pw(),
            http_post=fake_post,
            mode="direct",
        )
        assert out.get("ok") is False, line
        assert out.get("error") == "use_prepare_verb", line
        assert seen == [], line


def test_fr6079_allowlisted_ops_cannot_carry_a_prepare_name():
    """Every generic allowlisted op refuses a prepare ename/name with no SOAP."""
    assert "ProcNewReportMob" not in wcf._GENERIC_ALLOWED_OPS
    assert not any(op.startswith("ProcNewReport") for op in wcf._GENERIC_ALLOWED_OPS)
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    programs = (
        "FORMPREP",
        "FORMPREPDRCT",
        "FORMPREPDRCT2",
        "REPPREP",
        "REPPREPDIRECT2",
        "PROCPREP",
    )
    for op in sorted(wcf._GENERIC_ALLOWED_OPS):
        for key in ("ename", "name"):
            for prog in programs:
                seen.clear()
                line = (
                    f"PRIORITY wcf {op} type=P {key}={prog} "
                    "url=https://priority.example.invalid user=tabula"
                )
                out = wcf.run_priority_wcf(
                    line,
                    passed_password=_pw(),
                    http_post=fake_post,
                    mode="direct",
                )
                assert out.get("ok") is False, line
                assert out.get("error") == "use_prepare_verb", line
                assert seen == [], line


def test_fr6079_non_prepare_procstart_still_calls_and_form_ops_are_readonly():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, _result("ProcStartMob", {"Procedure": [{"session": "S", "step": ""}]})

    out = wcf.run_priority_wcf(
        "PRIORITY wcf ProcStart type=P ename=WWWSHOW "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert seen == ["ProcStartMob"]
    assert out.get("error") != "use_prepare_verb"

    seen.clear()
    blocked = wcf.run_priority_wcf(
        "PRIORITY wcf FormStartMob form=EFORM "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert blocked.get("ok") is False
    assert blocked.get("error") == wcf.WCF_READONLY
    assert seen == []

    report = wcf.run_priority_wcf(
        "PRIORITY wcf ProcNewReport type=P ename=WWWSHOW mode=H format=0 "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert report.get("ok") is False
    assert report.get("error") == wcf.WCF_READONLY
    assert seen == []


def _happy_post(actions: list[str], blobs: list[str]):
    stage = {"q": 0, "start": 0}

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        blobs.append(blob)
        if act == "FormStartMob":
            stage["start"] += 1
            if stage["start"] == 1:
                assert "<form>EFORM</form>" in blob
                assert "<scrwidth>-1</scrwidth>" in blob
                assert "<autoRetrieveFirstRows>false</autoRetrieveFirstRows>" in blob
                assert "<debug>false</debug>" in blob
                assert "<sendtitles>false</sendtitles>" in blob
                return 400, _result(act, _eform_start("S0"))
            assert "<form>FORMPREPERRS</form>" in blob
            assert "<autoRetrieveFirstRows>true</autoRetrieveFirstRows>" in blob
            return 400, _result(act, _form_doc("FORMPREPERRS", ERR_TABLE, "E0", ERR_COLS, []))
        if act == "FormQueryDlgExecuteMob":
            stage["q"] += 1
            assert "<ic>true</ic>" in blob
            assert "<queryname></queryname>" in blob or "<queryname />" in blob
            assert "<add>false</add>" in blob
            filt = _b64(
                json.dumps(
                    {
                        "or": 0,
                        "QueryValues": [
                            {
                                "field": ENAME_FIELD,
                                "fromval": "WWWSHOWCUST",
                                "toval": "",
                                "op": "=",
                                "sort": 0,
                                "isdesc": 0,
                            }
                        ],
                    },
                    separators=(",", ":"),
                )
            )
            if stage["q"] == 1:
                assert wcf.sdk_statexml("S0", 0, 1, "") in blob
                assert "<top>19</top>" in blob
                assert filt in blob
                return 400, _result(
                    act,
                    _eform_rows([(3, {"ENAME": "WWWSHOWCUST", "TITLE": "Customers"})], "S1"),
                )
            err_filt = _b64(
                json.dumps(
                    {
                        "or": 0,
                        "QueryValues": [
                            {
                                "field": ERR_COLS[0]["field"],
                                "fromval": "WWWSHOWCUST",
                                "toval": "",
                                "op": "=",
                                "sort": 0,
                                "isdesc": 0,
                            }
                        ],
                    },
                    separators=(",", ":"),
                )
            )
            assert err_filt in blob
            assert filt not in blob
            assert "<top>9</top>" in blob
            assert wcf.sdk_statexml("E0", 0, 1, "") in blob
            return 400, _result(
                act,
                _form_doc(
                    "FORMPREPERRS",
                    ERR_TABLE,
                    "E1",
                    ERR_COLS,
                    [
                        (1, {"ENAME": "WWWSHOWCUST", "MESSAGE": "ok"}),
                        (2, {"ENAME": "OTHERFORM", "MESSAGE": "old"}),
                    ],
                    include_table=False,
                    position_field=2,
                ),
            )
        if act == "FormJumpLineMob":
            assert wcf.sdk_statexml("S1", ENAME_FIELD, 1, "") in blob
            assert "<line>3</line>" in blob
            return 400, _result(act, _form_doc("EFORM", EFORM_TABLE, "S2", EFORM_COLS, [], include_table=False, position_field=ENAME_FIELD, position_line=3))
        if act == "FormActivateMob":
            assert wcf.sdk_statexml("S2", ENAME_FIELD, 3, "") in blob
            assert "FORMPREPDRCT2" not in blob
            assert "<before>true</before>" in blob
            return 400, _result(
                act,
                _form_doc(
                    "EFORM",
                    EFORM_TABLE,
                    "S3",
                    EFORM_COLS,
                    [],
                    include_table=False,
                    activate={"table": "EFORM", "link": "ENAME", "linkid": "L79"},
                ),
            )
        if act == "ProcStartActivateMob":
            assert "L79" in blob
            assert "FORMPREPDRCT2" in blob
            assert "<avoidmessages>false</avoidmessages>" in blob
            return 400, _result(act, _proc_doc("S79", "", finished=1, message="ok"))
        if act == "FormExitFormMob":
            return 400, _result(act, {"Form": [{"Position": [{"session": "X"}]}]})
        if act == "ProcEndMob":
            return 400, _result(act, _proc_doc("S79", "", finished=1))
        raise AssertionError(act)

    return fake_post


def test_fr6079_prepare_uses_sdk_ops_and_statexml(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    monkeypatch.delenv("AIRC_CONSOLE_HOME", raising=False)
    actions: list[str] = []
    blobs: list[str] = []
    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=_happy_post(actions, blobs),
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "prepare_errors"
    assert out.get("ename") == "WWWSHOWCUST"
    assert out.get("errs") == 1
    assert out.get("rows") == [{"ENAME": "WWWSHOWCUST", "MESSAGE": "ok"}]
    assert out.get("last_type") == "end"
    jid = out.get("job_id") or ""
    assert re.fullmatch(r"[0-9a-f]{8}", jid)
    log = tmp_path / "jobs" / jid / "wcf-prepare.json"
    assert log.is_file()
    logged = json.loads(log.read_text(encoding="utf-8"))
    assert logged["row_ename"] == "WWWSHOWCUST"
    assert logged["activation"]["linkid"] == "L79"
    assert logged["activation"]["table"] == "EFORM"
    assert "FormSetSearchFilterMob" not in actions
    assert actions[:5] == [
        "FormStartMob",
        "FormQueryDlgExecuteMob",
        "FormJumpLineMob",
        "FormActivateMob",
        "ProcStartActivateMob",
    ]
    exit_blobs = [b for a, b in zip(actions, blobs) if a == "FormExitFormMob"]
    # Position.field 2 is the ENAME cell on line 1, so the memento value is that cell.
    assert any(wcf.sdk_statexml("E1", 2, 1, "WWWSHOWCUST") in b for b in exit_blobs)
    assert set(actions) <= wcf.PREPARE_SDK_OPS


def test_fr6079_ename_mismatch_one_wrong_row(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, _eform_start())
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(act, _eform_rows([(1, {"ENAME": "OTHERFORM"})]))
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"Form": [{"ok": True}]})
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
    assert out.get("job_id") == "aabb6079"
    assert "FormJumpLineMob" not in actions
    assert "ProcStartActivateMob" not in actions
    logged = json.loads((tmp_path / "jobs" / "aabb6079" / "wcf-prepare.json").read_text())
    assert logged["row_ename"] == "OTHERFORM"
    assert logged["activation"] is None


def test_fr6079_ename_compare_is_case_sensitive():
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, _eform_start())
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(act, _eform_rows([(1, {"ENAME": "Wwwshowcust"})]))
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"Form": [{"ok": True}]})
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
    assert "ProcStartActivateMob" not in actions


def test_fr6079_step_limit_kills():
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            blob = data.decode("utf-8")
            if "FORMPREPERRS" in blob:
                return 400, _result(act, _form_doc("FORMPREPERRS", ERR_TABLE, "E0", ERR_COLS, []))
            return 400, _result(act, _eform_start())
        if act == "FormQueryDlgExecuteMob":
            if actions.count("FormQueryDlgExecuteMob") > 1:
                return 400, _result(
                    act,
                    _form_doc(
                        "FORMPREPERRS",
                        ERR_TABLE,
                        "E1",
                        ERR_COLS,
                        [],
                        include_table=False,
                    ),
                )
            return 400, _result(act, _eform_rows([(1, {"ENAME": "WWWSHOWCUST"})]))
        if act == "FormJumpLineMob":
            return 400, _result(act, _form_doc("EFORM", EFORM_TABLE, "S2", EFORM_COLS, [], include_table=False))
        if act == "FormActivateMob":
            return 400, _result(
                act,
                _form_doc(
                    "EFORM",
                    EFORM_TABLE,
                    "S3",
                    EFORM_COLS,
                    [],
                    include_table=False,
                    activate={"table": "EFORM", "link": "ENAME", "linkid": "L"},
                ),
            )
        if act == "ProcStartActivateMob":
            return 400, _result(act, _proc_doc("SK", "displayurl"))
        if act == "ProcContinueMob":
            return 400, _result(act, _proc_doc("SK", "displayurl"))
        if act == "ProcKillProcessMob":
            return 400, _result(act, _proc_doc("SK", "", finished=1))
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"Form": [{"Position": [{"session": "Z"}]}]})
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
    assert actions.count("ProcContinueMob") == wcf.PREPARE_STEP_MAX - 1


def test_fr6079_log_fallback_and_validation(monkeypatch):
    monkeypatch.delenv("AIRC_HOME", raising=False)
    monkeypatch.delenv("AIRC_CONSOLE_HOME", raising=False)
    out = wcf.run_priority_wcf(
        "PRIORITY wcf prepare form NOT-A-NAME "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=lambda *a, **k: (_ for _ in ()).throw(AssertionError("soap")),
        mode="direct",
    )
    assert out.get("error") == "ename_invalid"
    jid = out["job_id"]
    log = Path(tempfile.gettempdir()) / "airc-wcf-prepare" / "jobs" / jid / "wcf-prepare.json"
    assert log.is_file()
    body = json.loads(log.read_text(encoding="utf-8"))
    assert body["error"] == "ename_invalid"
    assert _pw() not in log.read_text(encoding="utf-8")


class _EmptyAllow:
    def get(self, ident):
        return None


def test_fr6079_unknown_instance_writes_job_log(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    monkeypatch.delenv("AIRC_CONSOLE_HOME", raising=False)
    seen = []
    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf GetVersion missing-box",
        allowlist=_EmptyAllow(),
        passed_password=_pw(),
        http_post=lambda *a, **k: seen.append("soap") or (200, ""),
        mode="relay",
    )
    assert out.get("ok") is False
    assert out.get("error") == "unknown-instance"
    assert out.get("job_id") == "aabb6079"
    assert seen == []
    log = tmp_path / "jobs" / "aabb6079" / "wcf-prepare.json"
    assert log.is_file()
    body = json.loads(log.read_text(encoding="utf-8"))
    assert body["error"] == "unknown-instance"
    assert _pw() not in log.read_text(encoding="utf-8")


def test_fr6079_priority_not_installed_writes_job_log(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    monkeypatch.delenv("AIRC_CONSOLE_HOME", raising=False)
    seen = []
    out = wcf.run_priority_wcf(
        "id=bb6079aa PRIORITY wcf GetVersion "
        "url=https://priority.example.invalid user=tabula",
        allowlist_present=False,
        passed_password=_pw(),
        http_post=lambda *a, **k: seen.append("soap") or (200, ""),
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "priority_not_installed"
    assert out.get("job_id") == "bb6079aa"
    assert seen == []
    log = tmp_path / "jobs" / "bb6079aa" / "wcf-prepare.json"
    assert log.is_file()
    logged = log.read_text(encoding="utf-8")
    assert json.loads(logged)["error"] == "priority_not_installed"
    assert _pw() not in logged


def test_fr6079_log_oserror_sets_log_write_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    monkeypatch.delenv("AIRC_CONSOLE_HOME", raising=False)
    real = Path.write_text

    def boom(self, *args, **kwargs):
        if self.name == "wcf-prepare.json":
            raise OSError("disk full")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", boom)
    out = wcf.run_priority_wcf(
        "id=cc6079bb PRIORITY wcf prepare form NOT-A-NAME "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=lambda *a, **k: (_ for _ in ()).throw(AssertionError("soap")),
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "ename_invalid"
    assert out.get("log_write_failed") is True
    assert out.get("job_id") == "cc6079bb"
    assert not (tmp_path / "jobs" / "cc6079bb" / "wcf-prepare.json").is_file()


def test_fr6079_pack_omits_vendored_sdk_index():
    pack = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "scripts"
        / "Pack-BobiverseRelease.ps1"
    ).read_text(encoding="utf-8-sig")
    assert "$_.Name -ne 'priority-web-sdk'" in pack
    assert "sdk/priority-web-sdk/index.js is the test fixture" in pack
    assert "node_modules\\priority-web-sdk" in pack or "node_modules/priority-web-sdk" in pack


def test_fr6079_console_done_id_is_prepare_log_id(monkeypatch):
    monkeypatch.setattr(ac._priority, "priority_runtime_available", lambda *a, **k: True)

    def fake_run(text, **kwargs):
        return {
            "ok": True,
            "action": "wcf",
            "op": "prepare",
            "ename": "WWWSHOWCUST",
            "job_id": "cafebabe",
            "steps": 1,
            "last_type": "end",
            "errs": 0,
        }

    monkeypatch.setattr(wcf, "run_priority_wcf", fake_run)
    core = ac.AircConsoleCore(
        machine="flamingo",
        auth=ops_auth("bob-flamingo", channel="#flamingo"),
        nick="flamingo_console",
        install_root=str(Path(__file__).resolve().parents[2] / "no-such-airc-root"),
    )
    hr = core.handle_raw(
        ":bob-flamingo!u@h PRIVMSG flamingo_console "
        ":PRIORITY wcf prepare form WWWSHOWCUST"
    )
    assert hr is not None
    assert "DONE id=cafebabe" in (hr.reply or "")


def _form_shell(act: str, blob: str, stage: dict[str, int], *, linkid: str = "L79"):
    """EFORM open/search/jump/activate plus a later FORMPREPERRS read. None if not a form op."""
    if act == "FormStartMob":
        stage["start"] += 1
        if stage["start"] == 1:
            return 400, _result(act, _eform_start("S0"))
        return 400, _result(act, _form_doc("FORMPREPERRS", ERR_TABLE, "E0", ERR_COLS, []))
    if act == "FormQueryDlgExecuteMob":
        stage["q"] += 1
        if stage["q"] == 1:
            assert wcf.sdk_statexml("S0", 0, 1, "") in blob
            return 400, _result(act, _eform_rows([(1, {"ENAME": "WWWSHOWCUST"})], "S1"))
        return 400, _result(
            act,
            _form_doc("FORMPREPERRS", ERR_TABLE, "E1", ERR_COLS, [], include_table=False),
        )
    if act == "FormJumpLineMob":
        assert "<line>1</line>" in blob
        return 400, _result(
            act,
            _form_doc(
                "EFORM",
                EFORM_TABLE,
                "S2",
                EFORM_COLS,
                [],
                include_table=False,
                position_field=ENAME_FIELD,
                position_line=1,
            ),
        )
    if act == "FormActivateMob":
        assert wcf.sdk_statexml("S2", ENAME_FIELD, 1, "") in blob
        assert "<before>true</before>" in blob
        return 400, _result(
            act,
            _form_doc(
                "EFORM",
                EFORM_TABLE,
                "S3",
                EFORM_COLS,
                [],
                include_table=False,
                activate={"table": "EFORM", "link": "ENAME", "linkid": linkid},
            ),
        )
    if act in {"FormExitFormMob", "ProcEndMob"}:
        return 400, _result(act, {"Form": [{"Position": [{"session": "Z"}]}]})
    return None


def test_fr6079_step_dispatch_matches_sdk_builders():
    """newsaved/askprint/CLIENT/warning use the SDK ops, not ProcContinueMob."""
    procs = [
        _proc_doc("P1", "input", message="careful", messagetype="warning"),
        _proc_doc(
            "P2",
            "newsaved",
            extra={"Formats": [{"format": 12, "selected": 1}]},
        ),
        _proc_doc(
            "P3",
            "input",
            extra={"Parameters": [{"EditField": [{"field": 7, "title": "Form Name", "value": ""}]}]},
        ),
        _proc_doc(
            "P4",
            "input",
            extra={"Parameters": [{"ChooseField": [{"field": 3, "selected": 1}]}]},
        ),
        _proc_doc(
            "P5",
            "askprint",
            extra={"AskPrint": [{"Formats": [{"format": 5, "selected": 1}]}]},
        ),
        _proc_doc("P6", "CLIENT"),
        _proc_doc("P7", "", finished=1),
    ]
    stage = {"q": 0, "start": 0, "proc": 0}
    seen: list[tuple[str, str]] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        seen.append((act, blob))
        formed = _form_shell(act, blob, stage)
        if formed is not None:
            return formed
        if act == "ProcStartActivateMob":
            assert "<avoidmessages>false</avoidmessages>" in blob
            assert "L79" in blob
            return 400, _result(act, procs[0])
        stage["proc"] += 1
        nxt = procs[stage["proc"]]
        if act == "ProcWarningOKMob":
            assert "<warnings>0</warnings>" in blob
        elif act == "ProcNewReportMob":
            assert "<ename>FORMPREPDRCT2</ename>" in blob
            assert "<debug>false</debug>" in blob
            assert "<mode>H</mode>" in blob
            assert "<format>12</format>" in blob
        elif act == "ProcEditFieldsOKMob":
            assert "<save>false</save>" in blob
            edit = wcf._b64_text(
                wcf._gwt_json(
                    {"EditFields": [{"field": 7, "op": 0, "value": "WWWSHOWCUST"}]}
                )
            )
            assert edit in blob
        elif act == "ProcChooseFieldsOKMob":
            assert "<field>3</field>" in blob
        elif act == "ProcAskPrintOKMob":
            assert "<mode>2</mode>" in blob
            assert "<format>5</format>" in blob
            assert "<pdf>true</pdf>" in blob
            assert "<sendattach>false</sendattach>" in blob
            assert "<copies>1</copies>" in blob
        elif act == "ProcClientContinueMob":
            assert f"<data>{wcf._client_data_b64()}</data>" in blob
            assert wcf._client_data_b64() == "IiI="
        else:
            raise AssertionError(act)
        return 400, _result(act, nxt)

    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is True, out
    assert out.get("errs") == 0
    assert out.get("last_type") == "end"
    names = [a for a, _b in seen]
    assert names[names.index("ProcStartActivateMob") + 1 : names.index("FormStartMob", 1)] == [
        "ProcWarningOKMob",
        "ProcNewReportMob",
        "ProcEditFieldsOKMob",
        "ProcChooseFieldsOKMob",
        "ProcAskPrintOKMob",
        "ProcClientContinueMob",
    ]
    assert "ProcContinueMob" not in names


def test_fr6079_unknown_step_kills():
    actions: list[str] = []
    stage = {"q": 0, "start": 0}

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        blob = data.decode("utf-8")
        actions.append(act)
        formed = _form_shell(act, blob, stage)
        if formed is not None:
            return formed
        if act == "ProcStartActivateMob":
            return 400, _result(act, _proc_doc("SK", "not-a-real-step"))
        if act == "ProcKillProcessMob":
            assert "<session>SK</session>" in blob
            return 400, _result(act, _proc_doc("SK", "", finished=1))
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6079 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert out.get("error") == "unknown_step"
    assert "ProcKillProcessMob" in actions
    assert "ProcEndMob" in actions
