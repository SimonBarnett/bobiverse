"""FR #6018: sqlcmd form walk stays in IRC budget; form table from dictionary."""
from __future__ import annotations

import json
from pathlib import Path

import airc_console as ac
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


def _fat_rows(n: int = 5, cols: int = 10):
    columns = [f"C{i:02d}" for i in range(cols)]
    rows = [{c: f"{c}-r{r}-xxxxxxxx" for c in columns} for r in range(n)]
    return columns, rows


def test_fr6018_walk_success_stays_in_budget_without_rows():
    columns, rows = _fat_rows()
    payload = {
        "ok": True,
        "action": "walk",
        "op": "formStart",
        "form": "CUSTOMERS",
        "table": "CUSTOMERS",
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "offset": 0,
        "limit": 5,
        "readonly": True,
        "via": "sql",
        "instance": "hrs-dev-live1",
    }
    raw = "out id=aabb6018 seq=1 " + json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    )
    assert len(raw.encode("utf-8")) > ap.PRIORITY_REPLY_MAX_BYTES
    out, exit_code = ap.format_bounded_priority_out("aabb6018", payload, 0)
    assert exit_code == 0
    assert len(out.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(out.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert body.get("error") != "reply-too-large"
    assert body.get("form") == "CUSTOMERS"
    assert body.get("count") == 5
    assert "columns" in body
    assert "rows" not in body


def test_fr6018_form_table_from_dictionary_not_form_name():
    """Acceptance: form ENAME and physical table differ (dictionary TNAME)."""
    seen_q = []

    def runner(argv, **kw):
        q = " ".join(str(a) for a in argv)
        seen_q.append(q)

        class P:
            returncode = 0
            stderr = ""
            stdout = ""

        up = q.upper()
        if "T$EXEC" in up:
            P.stdout = "CUSTORDERS|42|F|\n"
            return P()
        if "FROM DBO.EXEC" in up or "FROM DBO.[EXEC]" in up or "COLUMNS" in up:
            P.stdout = "ORDERS\n"
            return P()
        if "FROM DBO.[ORDERS]" in up:
            P.stdout = "ORDNAME|ORDDES\nA|One\n"
            return P()
        if "FROM DBO.[CUSTORDERS]" in up:
            raise AssertionError("must not query table==form when dictionary has TNAME")
        P.returncode = 1
        return P()

    out = ac._priority_sql_formwalk(
        op="formStart",
        form="CUSTORDERS",
        instance=_inst(),
        sql_runner=runner,
    )
    assert out.get("ok") is True
    assert out.get("form") == "CUSTORDERS"
    assert out.get("table") == "ORDERS"
    assert "ORDNAME" in (out.get("columns") or [])
    blob = "\n".join(seen_q).upper()
    assert "DBO.[ORDERS]" in blob
    assert "DBO.[CUSTORDERS]" not in blob
    # EXEC is reserved T-SQL; live sqlcmd needs delimited identifiers.
    assert "FROM DBO.[EXEC]" in blob
    assert "WHERE [EXEC]=" in blob


def test_fr6018_run_walk_irc_ok_and_rows_on_job_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRC_HOME", str(tmp_path))
    columns, rows = _fat_rows()

    def sql(**kw):
        return {
            "ok": True,
            "op": "formStart",
            "form": "CUSTOMERS",
            "table": "CUSTOMERS",
            "columns": columns,
            "rows": rows,
            "count": len(rows),
            "via": "sql",
        }

    r = ap.run_priority_walk(
        text="id=aabb6018 PRIORITY formStart instance=hrs-dev-live1 form=CUSTOMERS",
        allowlist_path=_allow(tmp_path),
        sdk_walk=sql,
    )
    assert r.ok is True
    assert r.exit_code == 0
    line = r.lines[0]
    assert len(line.encode("utf-8")) <= ap.PRIORITY_REPLY_MAX_BYTES
    body = json.loads(line.split("seq=1 ", 1)[1])
    assert body.get("ok") is True
    assert "rows" not in body
    ref = r.payload.get("rows_ref") or body.get("rows_ref")
    assert ref
    saved = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert saved.get("count") == 5
    assert len(saved.get("rows") or []) == 5
