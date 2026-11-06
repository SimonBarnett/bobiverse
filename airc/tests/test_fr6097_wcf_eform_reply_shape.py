"""FR #6097: parse live EFORM FormStartMob shapes; honest errs; cleanup."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import airc_priority as ap
import priority_wcf as wcf

from test_fr6058_wcf_400_success_and_mob_decode import _b64, _result_envelope
from test_fr6079_wcf_prepare_sdk_scope import (
    EFORM_TABLE,
    ENAME_FIELD,
    _act,
    _column,
    _eform_rows,
    _form_doc,
    _fv,
    _pw,
    _result,
)


def _title_col(name: str, field: int, height: int = 20) -> dict:
    """sendtitles=false live shape: zoomname empty, title holds the field name."""
    return {"zoomname": "", "title": name, "field": field, "height": height, "type": 1, "width": 20}


def test_fr6097_mixed_case_prepare_ename_hits_generic_guard():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(_act(headers))
        return 400, ""

    out = wcf.run_priority_wcf(
        "PRIORITY wcf ProcStartMob type=P ename=FormPrep "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("error") == "use_prepare_verb"
    assert seen == []


def test_fr6097_title_only_columns_resolve_ename(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    cols = [_title_col("ENAME", ENAME_FIELD), _title_col("TITLE", 5, 8)]
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        blob = (data or b"").decode("utf-8", errors="replace")
        if act == "FormStartMob":
            if "EFORM" in blob:
                return 400, _result(
                    act,
                    _form_doc("EFORM", EFORM_TABLE, "S0", cols, []),
                )
            return 400, _result(
                act,
                _form_doc(
                    "FORMPREPERRS",
                    11,
                    "E0",
                    [_title_col("ENAME", 2, 10)],
                    [],
                ),
            )
        if act == "FormQueryDlgExecuteMob":
            return 400, _result(
                act,
                _form_doc(
                    "EFORM",
                    EFORM_TABLE,
                    "S1",
                    [_column("ENAME", ENAME_FIELD), _column("TITLE", 5, 8)],
                    [(1, {"ENAME": "WWWSHOWCUST"})],
                    include_table=False,
                    position_field=ENAME_FIELD,
                ),
            )
        if act == "FormJumpLineMob":
            return 400, _result(act, _eform_rows([(1, {"ENAME": "WWWSHOWCUST"})], "S2"))
        if act == "FormActivateMob":
            return 400, _result(
                act,
                _form_doc(
                    "EFORM",
                    EFORM_TABLE,
                    "S3",
                    cols,
                    [],
                    include_table=False,
                    activate={"table": "EFORM", "link": "ENAME", "linkid": "L1"},
                ),
            )
        if act == "ProcStartActivateMob":
            return 400, _result(
                act,
                {"Procedure": [{"session": "P1", "step": "X", "finished": 1}]},
            )
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6097 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    # FR #6108: title is not zoomname; SDK mapping must not guess.
    assert out.get("error") == "ename_column_missing", out
    assert "FormActivateMob" not in actions
    assert "ProcStartActivateMob" not in actions


def test_fr6097_form_c_columns_resolve_ename():
    form = {
        "Position": [{"session": "S0", "table": EFORM_TABLE, "field": ENAME_FIELD, "line": 1}],
        "C": [{"field": ENAME_FIELD, "zoomname": "ENAME"}, {"field": 5, "name": "TITLE"}],
        "NewTable": [{"table": EFORM_TABLE, "name": "EFORM", "NewColumn": []}],
        "RT": [_fv(EFORM_TABLE, ENAME_FIELD, 1, "WWWSHOWCUST")],
    }
    meta = wcf._FormMeta()
    meta.absorb(form)
    assert meta.ename_field(EFORM_TABLE) == ENAME_FIELD
    rows = wcf._live_rows(form, EFORM_TABLE, meta)
    assert [r.get("ENAME") for r in rows] == ["WWWSHOWCUST"]


def test_fr6097_early_fail_logs_reply_shape_and_honest_errs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(
                act,
                {
                    "Form": [
                        {
                            "Position": [{"session": "S0", "table": 10, "field": 0, "line": 1}],
                            "NewTable": [
                                {
                                    "table": 10,
                                    "name": "EFORM",
                                    "NewColumn": [
                                        {"field": 1, "zoomname": "", "title": ""},
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )
        if act in {"FormExitFormMob", "ProcEndMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=cafef00d PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("error") == "ename_column_missing"
    assert out.get("errs") is None
    assert "ProcEndMob" not in actions
    assert "FormExitFormMob" in actions
    log = json.loads((tmp_path / "jobs" / "cafef00d" / "wcf-prepare.json").read_text(encoding="utf-8"))
    shapes = log.get("form_start_shapes") or []
    shape = shapes[0] if shapes else (log.get("form_start_shape") or log.get("reply_shape"))
    assert isinstance(shape, dict), log
    assert "keys" in shape
    assert "columns" in shape
    assert "row_count" in shape
    assert "decoded_len" in shape
    blob = json.dumps(shape)
    assert "WWWSHOWCUST" not in blob or "ENAME" in blob


def test_fr6097_companies_trim_keeps_op_via_and_truncated_flag():
    names = [f"co{i:02d}" for i in range(21)]
    names[1] = "live1"
    payload = [{"DNAME": n, "DBNAME": n + "db"} for n in names]
    xml = _result_envelope("GeneralCompaniesMob", _b64(json.dumps(payload)))
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, xml),
    ).general_companies()
    out["action"] = "wcf"
    framed, code = ap.format_bounded_priority_out("aabb6097", out, 0)
    assert code == 0
    body = json.loads(framed.split("seq=1 ", 1)[1])
    assert body.get("op")
    assert body.get("via")
    assert "endpoint_ok" in body
    if len(body.get("companies") or []) < 21:
        assert body.get("truncated") is True
    assert "live1" in (body.get("companies") or [])
