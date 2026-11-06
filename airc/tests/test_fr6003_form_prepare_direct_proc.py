"""FR #6003: typed prepare form uses WINRUN direct prepare, not web SDK/API."""
from __future__ import annotations

import sys
from pathlib import Path

from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import airc_console as ac  # noqa: E402
import priority_worker as pw  # noqa: E402

INST = {
    "id": "hrs-dev-live1",
    "url": "https://prioritydev.example.invalid",
    "company": "live1",
    "user": "tabula",
    "credentialTarget": "PriorityWeb/hrs-dev-live1",
    "sqlServer": ".\\PRI",
    "systemDb": "system",
    "prepDir": "E:\\priority\\system\\prep",
    "priorityRoot": "E:\\priority",
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


def test_fr6003_form_prepare_uses_winrun_not_sdk(tmp_path, monkeypatch):
    """Default form prepare must call WINRUN, never node/priority-web-sdk mjs."""
    root = tmp_path / "priority"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    winrun = bin_dir / "WINRUN.EXE"
    winrun.write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_WINRUN", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        seen["kw"] = kw

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    out = ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "url": "https://example.invalid",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(root),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("ok") is True
    assert out.get("runner") == "winrun"
    argv = seen["argv"]
    joined = " ".join(str(a).replace("\\", "/") for a in argv)
    assert "WINRUN" in joined.upper()
    assert "WINACTIV" in argv
    assert "-P" in argv
    assert "FORMPREP" in argv
    assert "run-repprep-via-exec.mjs" not in joined
    assert "run-formprep-via-eform.mjs" not in joined
    assert "node" not in argv[0].lower()
    assert "priority-web-sdk" not in joined
    # Password is on argv for WINRUN but must not appear in returned payload.
    blob = str(out)
    assert "secret-placeholder-priority-pw" not in blob


def test_fr6003_form_prepare_dispatch_never_loads_sdk_module(tmp_path, monkeypatch):
    """Acceptance: no priority-web-sdk import/login on default form prepare path."""
    root = tmp_path / "priority"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "WINRUN.EXE").write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")

    def boom_sdk(**kw):
        raise AssertionError("web SDK runner must not be called for default form prepare")

    monkeypatch.setattr(ac, "_priority_sdk_repprep", boom_sdk)

    def fake_run(argv, **kw):
        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    out = ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(root),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("ok") is True
    assert out.get("runner") == "winrun"


def test_fr6003_form_via_eform_opt_in_only(tmp_path, monkeypatch):
    """FR #6108: AIRC_PRIORITY_FORM_VIA_EFORM no longer selects the unscoped SDK path."""
    pri = tmp_path / "priority"
    (pri / "bin").mkdir(parents=True)
    (pri / "bin" / "WINRUN.EXE").write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    monkeypatch.setenv("AIRC_PRIORITY_FORM_VIA_EFORM", "1")
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EXEC", raising=False)
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")
    monkeypatch.setattr(
        ac,
        "_priority_sdk_repprep",
        lambda **kw: (_ for _ in ()).throw(AssertionError("SDK form path removed")),
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    out = ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(pri),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("runner") == "winrun"
    joined = " ".join(str(a).replace("\\", "/") for a in (seen.get("argv") or []))
    assert "run-formprep-via-eform.mjs" not in joined


def test_fr6003_form_via_exec_opt_in_only(tmp_path, monkeypatch):
    """FR #6108: AIRC_PRIORITY_FORM_VIA_EXEC no longer starts FORMPREPDRCT2 via SDK."""
    pri = tmp_path / "priority"
    (pri / "bin").mkdir(parents=True)
    (pri / "bin" / "WINRUN.EXE").write_text("stub", encoding="utf-8")
    prep = tmp_path / "prep"
    prep.mkdir()
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.setenv("AIRC_PRIORITY_FORM_VIA_EXEC", "1")
    monkeypatch.setenv(ac._WINRUN_ARGV_OPTIN, "1")
    monkeypatch.setattr(
        ac,
        "_priority_sdk_repprep",
        lambda **kw: (_ for _ in ()).throw(AssertionError("SDK form path removed")),
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    out = ac._priority_prepare_exec(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "user": "tabula",
            "prepDir": str(prep),
            "priorityRoot": str(pri),
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        process_runner=fake_run,
    )
    assert out.get("runner") == "winrun"
    joined = " ".join(str(a).replace("\\", "/") for a in (seen.get("argv") or []))
    assert "run-repprep-via-exec.mjs" not in joined


def test_fr6003_typed_form_still_selects_f_row_and_formprep_proc(tmp_path):
    """Typed F checks stay; worker still names FORMPREPDRCT2 for the form row."""
    prep = tmp_path / "prep"
    prep.mkdir()
    inst = dict(INST)
    inst["prepDir"] = str(prep)
    seen = {}

    def sdk(**kw):
        seen.update(kw)
        return {"ok": True, "path": kw.get("path"), "runner": "winrun"}

    def types(**kw):
        return [
            {"name": "CUSTOMERS", "exec_id": 13, "exec_type": "F", "upd": "Y"},
            {"name": "CUSTOMERS", "exec_id": 296, "exec_type": "R", "upd": "Y"},
        ]

    r = pw.run_priority_prepare(
        "CUSTOMERS",
        instance_id="hrs-dev-live1",
        instances=[inst],
        exec_type="F",
        resolve_ename_types=types,
        **_hooks(sdk_exec=sdk),
    )
    assert r["ok"] is True
    assert int(r["exec_id"]) == 13
    assert r["exec"] == "FORMPREPDRCT2"
    assert seen.get("path") == "FORMPREPDRCT2"
    assert seen.get("exec_type") == "F"
    assert seen.get("form_prep") is True


def test_fr6003_hooks_wire_prepare_exec_dispatcher():
    """Console prepare hooks must dispatch through _priority_prepare_exec."""
    src = (ROOT / "airc" / "scripts" / "airc_console.py").read_text(encoding="utf-8")
    assert "sdk_exec=lambda **kw: _priority_prepare_exec(" in src
    assert "_priority_winrun_formprep" in src
    assert "no EFORM/EXEC SDK opt-in" in src
    assert "_WINRUN_ARGV_OPTIN" in src
