"""FR #5991: live form walk is SQL (no priority-web-sdk / formStart)."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
import airc_fail_intake as fi
import airc_priority as ap


def _inst() -> dict:
    return {
        "id": "hrs-dev-live1",
        "url": "https://prioritydev.example.invalid",
        "company": "live1",
        "user": "tabula",
        "credentialTarget": "PriorityWeb/hrs-dev-live1",
        "sqlServer": ".\\PRI",
        "systemDb": "system",
    }


def _allow(tmp_path: Path) -> Path:
    p = tmp_path / "priority-instances.json"
    p.write_text(json.dumps({"instances": [_inst()]}), encoding="utf-8")
    return p


def test_fr5991_sql_formwalk_returns_rows_without_node_or_formstart():
    seen = []

    def runner(argv, **kw):
        seen.append(list(argv))
        q = " ".join(argv).upper()
        class P:
            returncode = 0
            stderr = ""
            stdout = ""
        if "T$EXEC" in q or "T$EXEC" in " ".join(argv):
            P.stdout = "CUSTOMERS|13|F|\n"
            return P()
        P.stdout = (
            "CUSTNAME|CUSTDES\n"
            "--------|--------\n"
            "A|Acme\n"
            "B|Beta\n"
        )
        return P()

    out = ac._priority_sql_formwalk(
        op="formStart",
        form="CUSTOMERS",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is True
    assert out.get("form") == "CUSTOMERS"
    assert "CUSTNAME" in (out.get("columns") or [])
    assert out.get("rows")
    assert out.get("count") == 2
    blob = json.dumps(seen).lower()
    assert "node" not in blob
    assert "formstart" not in blob
    assert "priority-web-sdk" not in blob
    assert "run-formwalk-readonly" not in blob


def test_fr5991_sql_formwalk_unknown_form_no_intake(tmp_path, monkeypatch):
    reports = []
    monkeypatch.setattr(fi, "report_verb_failure", lambda *a, **kw: reports.append((a, kw)))

    def sql(**kw):
        return {"ok": False, "error": "form-not-found", "form": "NOPE"}

    r = ap.run_priority_walk(
        text="id=aabb5991 PRIORITY formStart instance=hrs-dev-live1 form=NOPE",
        allowlist_path=_allow(tmp_path),
        sdk_walk=sql,
    )
    assert not r.ok
    assert r.payload["error"] == "form-not-found"
    assert reports == []


def test_fr5991_sql_missing_server_is_named_expected():
    inst = _inst()
    inst.pop("sqlServer")
    out = ac._priority_sql_formwalk(op="formStart", form="CUSTOMERS", instance=inst)
    assert out.get("ok") is False
    assert out.get("error") == "sql_missing"


def test_fr5991_default_walk_hook_is_sql_not_sdk(monkeypatch):
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_SDK", raising=False)
    called = {}

    def fake_sql(**kw):
        called["sql"] = True
        return {"ok": True, "op": "formStart", "form": "CUSTOMERS", "rows": [], "count": 0}

    def boom(**kw):
        raise AssertionError("sdk formwalk must not run by default")

    monkeypatch.setattr(ac, "_priority_sql_formwalk", fake_sql)
    monkeypatch.setattr(ac, "_priority_sdk_formwalk", boom)
    hook = ac._default_priority_formwalk
    out = hook(op="formStart", form="CUSTOMERS", instance=_inst())
    assert called.get("sql") is True
    assert out.get("ok") is True


def test_fr5991_walk_expected_includes_sql_tokens():
    assert "sql_missing" in ap._WALK_EXPECTED_ERRORS
    assert "sql_read_failed" in ap._WALK_EXPECTED_ERRORS


def test_fr5991_optin_mjs_does_not_construct_priority_class():
    from repo_layout import ROOT

    src = (ROOT / "airc" / "priority-worker" / "sdk" / "run-formwalk-readonly.mjs").read_text(
        encoding="utf-8"
    )
    assert "new Priority.Priority({" not in src
    assert "await priority.login({" in src
