"""FR #5946: PRIORITY prepare form|report|procedure <ENAME> (typed exact T$EXEC)."""
from __future__ import annotations

import sys

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402
import airc_console as ac

INST = {
    "id": "hrs-dev-live1",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "api-user",
    "credentialTarget": "PriorityWeb/hrs-dev-live1",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
    "prepDir": "E:\\priority\\system\\prep",
}


def _hooks(**over):
    h = {
        "cred_present": lambda target: True,
        "sdk_exec": lambda **kw: {"ok": True, "path": kw.get("path") or "REPPREPDIRECT2"},
        "read_upd": lambda **kw: "N",
        "prp_mtime_before": 100.0,
        "prp_mtime_after": lambda **kw: 200.0,
        "proc_type": "P",
    }
    h.update(over)
    return h


def test_parse_prepare_typed_and_untyped():
    u = ac.parse_priority_prepare_command("PRIORITY prepare FOO instance=hrs-dev-live1")
    assert u["name"] == "FOO" and not (u.get("exec_type") or u.get("kind"))
    f = ac.parse_priority_prepare_command("PRIORITY prepare form ORDERS instance=hrs-dev-live1")
    assert f["name"] == "ORDERS" and f.get("exec_type") == "F"
    r = ac.parse_priority_prepare_command("PRIORITY prepare report CUSTOMERS")
    assert r["name"] == "CUSTOMERS" and r.get("exec_type") == "R"
    p = ac.parse_priority_prepare_command("PRIORITY prepare procedure WWWSHOWCUST")
    assert p["name"] == "WWWSHOWCUST" and p.get("exec_type") == "P"
    t = ac.parse_priority_prepare_command("PRIORITY prepare name=ORDERS type=F")
    assert t["name"] == "ORDERS" and t.get("exec_type") == "F"


def test_fr5946_form_only_uses_formprep_not_repprep(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    seen = {}

    def sdk(**kw):
        seen.update(kw)
        return {"ok": True, "path": kw.get("path")}

    def types(**kw):
        return [{"name": "ORDERS", "exec_id": 22, "exec_type": "F", "upd": "Y"}]

    r = pw.run_priority_prepare(
        "ORDERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="F",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is True
    assert r["exec_type"] == "F"
    assert r["exec_id"] in (22, "22", 22)
    assert "d22" in str(r.get("prep_file") or r.get("prep_file_name") or "")
    assert r["exec"] == "FORMPREPDRCT2"
    assert seen.get("path") == "FORMPREPDRCT2"
    assert seen.get("form_prep") is True
    assert seen.get("exec_type") == "F"


def test_fr5946_report_only_uses_repprep(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    seen = {}

    def sdk(**kw):
        seen.update(kw)
        return {"ok": True, "path": kw.get("path")}

    def types(**kw):
        return [{"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": "Y"}]

    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="R",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is True
    assert r["exec_type"] == "R"
    assert int(r["exec_id"]) == 296
    assert "d296" in str(r.get("prep_file") or "")
    assert r["exec"] == "REPPREPDIRECT2"
    assert seen.get("form_prep") is not True
    assert seen.get("path") == "REPPREPDIRECT2"


def test_fr5946_form_plus_report_explicit_type_picks_exact_row(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    seen = {}

    def sdk(**kw):
        seen.update(kw)
        return {"ok": True, "path": kw.get("path")}

    def types(**kw):
        return [
            {"name": "CUSTOMERS", "exec_id": 13, "exec_type": "F", "upd": "Y"},
            {"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": "Y"},
            {"name": "CUSTOMERS", "exec_id": 99, "exec_type": "I", "upd": "Y"},
        ]

    form = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="F",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert form["ok"] is True and int(form["exec_id"]) == 13
    assert form["exec"] == "FORMPREPDRCT2"

    report = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="R",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert report["ok"] is True and int(report["exec_id"]) == 296
    assert report["exec"] == "REPPREPDIRECT2"


def test_fr5946_wrong_type_requested(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "FORMPREPDRCT2"}

    def types(**kw):
        return [{"name": "WWWSHOWCUST", "exec_id": 1, "exec_type": "P", "upd": "Y"}]

    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="F",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is False
    assert r["reason"] in {"wrong_type", "ename_not_found", "not_type_f"}
    assert "P" in str(r.get("exec_types") or "")
    assert sdk_calls["n"] == 0


def test_fr5946_untyped_prepare_still_procedure_only(tmp_path):
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)

    def types(**kw):
        return [
            {"name": "CUSTOMERS", "exec_id": 13, "exec_type": "F", "upd": "Y"},
            {"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": "Y"},
        ]

    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        # untyped / default procedure-only
        resolve_ename_types=types,
        **_hooks(),
    )
    assert r["ok"] is False
    assert r["reason"] in {"ename_ambiguous", "not_type_p"}
    assert "F" in r.get("exec_types", "") and "R" in r.get("exec_types", "")


def test_fr5946_unknown_exec_type_fails_closed(tmp_path):
    """Unknown type tokens must not coerce via first letter (PIZZA -> P)."""
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    sdk_calls = {"n": 0}

    def sdk(**kw):
        sdk_calls["n"] += 1
        return {"ok": True, "path": "REPPREPDIRECT2"}

    def types(**kw):
        return [{"name": "WWWSHOWCUST", "exec_id": 1, "exec_type": "P", "upd": "Y"}]

    r = pw.run_priority_prepare(
        "WWWSHOWCUST",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="PIZZA",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is False
    assert r["reason"] == "bad_exec_type"
    assert sdk_calls["n"] == 0

    bad = ac.parse_priority_prepare_command(
        "PRIORITY prepare name=WWWSHOWCUST type=PIZZA instance=hrs-dev-live1"
    )
    assert bad is not None
    assert not (bad.get("exec_type") or "")
