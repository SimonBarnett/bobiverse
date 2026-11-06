"""FR #6108: zoomname-only ENAME; safe reply shape; no empty ProcKill."""
from __future__ import annotations

import json

import priority_wcf as wcf

from test_fr6079_wcf_prepare_sdk_scope import EFORM_TABLE, ENAME_FIELD, _act, _pw, _result


def test_fr6108_short_fv_does_not_raise():
    blob = {"Form": [{"RT": [{"FV": "10\t4"}], "NewTable": []}]}
    form = wcf._form0(blob)
    shape = wcf._form_reply_shape(blob, form)
    assert shape["row_count"] == 0
    assert "decoded_len" in shape


def test_fr6108_title_is_not_ename_zoomname():
    form = {
        "NewTable": [
            {
                "table": EFORM_TABLE,
                "name": "EFORM",
                "NewColumn": [{"field": ENAME_FIELD, "zoomname": "", "title": "ENAME"}],
            }
        ]
    }
    meta = wcf._FormMeta()
    meta.absorb(form)
    assert meta.ename_field(EFORM_TABLE) is None


def test_fr6108_empty_session_skips_prockill(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, {"ok": False, "error": "boom"})
        if act in {"FormExitFormMob", "ProcEndMob", "ProcKillProcessMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6108 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("ok") is False
    assert "ProcKillProcessMob" not in actions
    log = json.loads((tmp_path / "jobs" / "aabb6108" / "wcf-prepare.json").read_text(encoding="utf-8"))
    assert log.get("form_start_shapes")
