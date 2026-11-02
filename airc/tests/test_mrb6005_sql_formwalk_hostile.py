"""MRB #6005 hostile pins for FR #5991 sqlcmd form walk."""
from __future__ import annotations

import airc_console as ac


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


def test_mrb6005_rejects_non_ident_form_without_sqlcmd():
    seen = []

    def runner(argv, **kw):
        seen.append(argv)
        raise AssertionError("sqlcmd must not run for illegal form names")

    out = ac._priority_sql_formwalk(
        op="formStart",
        form="CUSTOMERS; DROP TABLE x",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is False
    assert out.get("error") == "form-not-found"
    assert seen == []


def test_mrb6005_sqlcmd_is_trusted_no_password_on_argv():
    argv_seen = []

    def runner(argv, **kw):
        argv_seen.append(list(argv))

        class P:
            returncode = 0
            stderr = ""
            stdout = "CUSTOMERS|13|F|\n"

        if len(argv_seen) == 1:
            return P()
        P.stdout = "CUSTNAME\n--------\nA\n"
        return P()

    out = ac._priority_sql_formwalk(
        op="formStart",
        form="CUSTOMERS",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is True
    assert argv_seen
    blob = " ".join(" ".join(map(str, a)) for a in argv_seen).lower()
    assert argv_seen[0][0] == "sqlcmd"
    assert "-E" in argv_seen[0]
    assert "-U" not in argv_seen[0]
    assert "-P" not in argv_seen[0]
    assert "password" not in blob
    assert "tabula" not in blob


def test_mrb6005_optin_sdk_flag_skips_sql(monkeypatch):
    monkeypatch.setenv("AIRC_PRIORITY_FORM_VIA_SDK", "1")

    def boom(**kw):
        raise AssertionError("SQL walk must not run when SDK opt-in is set")

    def sdk(**kw):
        return {"ok": True, "via": "sdk", "op": "formStart"}

    monkeypatch.setattr(ac, "_priority_sql_formwalk", boom)
    monkeypatch.setattr(ac, "_priority_sdk_formwalk", sdk)
    out = ac._default_priority_formwalk(op="formStart", form="CUSTOMERS", instance=_inst())
    assert out.get("via") == "sdk"


def test_mrb6005_sql_exception_is_sql_read_failed():
    def runner(argv, **kw):
        raise OSError("sqlcmd missing")

    out = ac._priority_sql_formwalk(
        op="formStart",
        form="CUSTOMERS",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is False
    assert out.get("error") == "sql_read_failed"


def test_mrb6005_getrows_op_preserved():
    def runner(argv, **kw):
        class P:
            returncode = 0
            stderr = ""
            stdout = "CUSTOMERS|13|F|\n"

        q = " ".join(map(str, argv)).upper()
        if "SELECT *" in q or "OFFSET" in q:
            P.stdout = "CUSTNAME\n--------\nA\n"
        return P()

    out = ac._priority_sql_formwalk(
        op="getRows",
        form="CUSTOMERS",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is True
    assert out.get("op") == "getRows"


def test_mrb6005_subform_does_not_query():
    seen = []

    def runner(argv, **kw):
        seen.append(argv)
        raise AssertionError("subform must fail closed without SQL")

    out = ac._priority_sql_formwalk(
        op="subform",
        form="CUSTOMERS",
        path="SHIPTO",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is False
    assert out.get("error") == "subform-not-found"
    assert seen == []
