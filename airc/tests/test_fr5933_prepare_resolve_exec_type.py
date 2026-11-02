"""FR #5933: PRIORITY prepare resolves T$EXEC type before REPPREPDIRECT2.

Refuse form-only / form+report names before SDK so REPPREPDIRECT2 cannot
prepare a same-named report while the TYPE=P lock looks still_unprepared.
"""

from __future__ import annotations

import sys

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402
import airc_console as ac


INST = {
    "id": "example-dev",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "api-user",
    "credentialTarget": "PriorityWeb/example-dev",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
    "prepDir": "E:\\priority\\system\\prep",
}


def _ok_hooks(**over):
    h = {
        "cred_present": lambda target: True,
        "sdk_exec": lambda **kw: {"ok": True, "path": "REPPREPDIRECT2"},
        "read_upd": lambda **kw: "N",
        "prp_mtime_before": 1000.0,
        "prp_mtime_after": lambda **kw: 1001.0,
        "proc_type": "P",
        # Default: single procedure row (production resolve path).
        "resolve_ename_types": lambda **kw: [
            {"name": kw.get("ename"), "exec_id": 1, "exec_type": "P", "upd": "Y"}
        ],
    }
    h.update(over)
    return h


def test_fr5933_procedure_only_still_prepares():
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is True
    assert r["reason"] == "prepared"
    assert sdk_calls["n"] == 1


def test_fr5933_form_only_refuses_before_sdk():
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "ORDERS",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(
            sdk_exec=sdk,
            resolve_ename_types=lambda **kw: [
                {"name": "ORDERS", "exec_id": 22, "exec_type": "F", "upd": ""}
            ],
        ),
    )
    assert r["ok"] is False
    assert r["reason"] == "not_type_p"
    assert "F" in str(r.get("exec_types") or "")
    assert sdk_calls["n"] == 0


def test_fr5933_form_and_report_ambiguous_before_sdk():
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(
            sdk_exec=sdk,
            resolve_ename_types=lambda **kw: [
                {"name": "CUSTOMERS", "exec_id": 13, "exec_type": "F", "upd": ""},
                {"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": ""},
            ],
        ),
    )
    assert r["ok"] is False
    assert r["reason"] == "ename_ambiguous"
    assert sdk_calls["n"] == 0


def test_fr5933_sqlcmd_ename_rows_parses_multi_type(monkeypatch):
    """_priority_sqlcmd_ename_rows returns every TYPE for ENAME (no TYPE=P filter)."""
    stdout = (
        "CUSTOMERS|13|F|\n"
        "CUSTOMERS|296|R|\n"
        "(2 rows affected)\n"
    )

    class _Proc:
        def __init__(self):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    def fake_run(*a, **k):
        # Query must not force TYPE=P. argv: sqlcmd -S ... -Q <query> ...
        argv = list(a[0]) if a else []
        assert "-b" in argv  # MRB #5936: fail on SQL error
        q = ""
        if "-Q" in argv:
            q = str(argv[argv.index("-Q") + 1])
        assert "TYPE]=N'P'" not in q.replace(" ", "")
        assert "ENAME" in q
        return _Proc()

    rows = ac._priority_sqlcmd_ename_rows(
        ename="CUSTOMERS",
        instance=INST,
        runner=fake_run,
    )
    assert len(rows) == 2
    types = sorted(r["exec_type"] for r in rows)
    assert types == ["F", "R"]


def test_mrb5936_sqlcmd_nonzero_exit_is_sql_read_failed_not_procedure():
    """Failed sqlcmd with a partial P row must not run the SDK (CodeRabbit major)."""
    sdk_calls = {"n": 0}

    class _Proc:
        def __init__(self):
            # Partial stdout that would look like a single procedure if trusted.
            self.stdout = "FOO|1|P|Y\n"
            self.stderr = "Sqlcmd: Error: ..."
            self.returncode = 1

    def fake_run(*a, **k):
        argv = list(a[0]) if a else []
        assert "-b" in argv
        return _Proc()

    def types_reader(*, ename, instance):
        return ac._priority_sqlcmd_ename_rows(
            ename=ename, instance=instance, runner=fake_run
        )

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(
            sdk_exec=sdk,
            resolve_ename_types=lambda **kw: types_reader(**kw),
        ),
    )
    assert r["ok"] is False
    assert r["reason"] == "sql_read_failed"
    assert sdk_calls["n"] == 0


def test_fr5933_default_hooks_resolve_before_sdk():
    seen = {"sdk": 0, "types": 0}

    def types_reader(*, ename, instance):
        seen["types"] += 1
        return [{"name": ename, "exec_id": 9, "exec_type": "F", "upd": ""}]

    def sdk_exec(**kw):
        seen["sdk"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    hooks = pw.build_default_prepare_hooks(
        cred_fetcher=lambda t: "secret" + "-placeholder-" + "x",
        lock_reader=lambda **k: {
            "name": k.get("ename"),
            "exec_id": 9,
            "exec_type": "P",
            "upd": "N",
        },
        types_reader=types_reader,
        sdk_exec=sdk_exec,
        prp_stat=lambda **k: 1.0,
    )
    r = pw.run_priority_prepare(
        "ORDERS", instance_id="example-dev", instances=[INST], **hooks
    )
    assert r["reason"] == "not_type_p"
    assert seen["types"] >= 1
    assert seen["sdk"] == 0
