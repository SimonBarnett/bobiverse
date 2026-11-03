"""FR #6113: Form-level Error/fatalerror is form_error, never ename_column_missing."""
from __future__ import annotations

import json

import priority_wcf as wcf

from test_fr6058_wcf_400_success_and_mob_decode import _b64, _result_envelope
from test_fr6079_wcf_prepare_sdk_scope import _act, _pw, _result


def _form_error_doc(text: str = "No API Licence") -> dict:
    return {"Form": [{"Error": text, "fatalerror": True}]}


def test_fr6113_form_error_no_ename_lookup_or_activate(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    actions: list[str] = []

    def fake_post(url, data, headers, timeout_s=30.0):
        act = _act(headers)
        actions.append(act)
        if act == "FormStartMob":
            return 400, _result(act, _form_error_doc())
        if act in {"FormExitFormMob", "ProcEndMob", "ProcKillProcessMob"}:
            return 400, _result(act, {"ok": True})
        raise AssertionError(act)

    out = wcf.run_priority_wcf(
        "id=aabb6113 PRIORITY wcf prepare form WWWSHOWCUST "
        "url=https://priority.example.invalid user=tabula",
        passed_password=_pw(),
        http_post=fake_post,
        mode="direct",
    )
    assert out.get("error") == "form_error", out
    assert out.get("ok") is False
    assert "No API Licence" in str(out.get("form_error") or out.get("last_message") or "")
    assert actions.count("FormStartMob") == 1
    assert "FormQueryDlgExecuteMob" not in actions
    assert "FormActivateMob" not in actions
    assert "ProcStartActivateMob" not in actions
    log = json.loads((tmp_path / "jobs" / "aabb6113" / "wcf-prepare.json").read_text(encoding="utf-8"))
    assert log.get("error") == "form_error"
    assert "No API Licence" in str(log.get("form_error") or "")


def test_fr6113_relay_http_400_form_error_is_not_ok():
    xml = _result_envelope("FormStartMob", _b64(json.dumps(_form_error_doc("licence"))))
    out = wcf.PriorityWcfClient(
        {"url": "https://priority.example.invalid", "user": "tabula", "company": "live1"},
        passed_password=_pw(),
        http_post=lambda *a, **k: (400, xml),
        mode="relay",
    ).call("FormStartMob", fields={"form": "EFORM"})
    assert out.get("ok") is False
    assert out.get("error") == "form_error"
    assert "licence" in str(out.get("form_error") or "")
