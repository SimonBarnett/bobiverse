"""FR #6003: typed prepare form uses direct procStart path, not EFORM/API."""
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


def test_fr6003_form_prepare_uses_repprep_mjs_not_eform(tmp_path, monkeypatch):
    """Default form prepare must call run-repprep-via-exec.mjs with FORMPREPDRCT2."""
    root = tmp_path / "airc-install"
    pw_dir = root / "airc" / "priority-worker" / "sdk"
    pw_dir.mkdir(parents=True)
    (pw_dir / "run-repprep-via-exec.mjs").write_text("// stub repprep\n", encoding="utf-8")
    (pw_dir / "run-formprep-via-eform.mjs").write_text("// stub eform\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.delenv("AIRC_PRIORITY_FORM_VIA_EFORM", raising=False)
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        class P:
            returncode = 0
            stdout = '{"ok":true,"ended":true,"errors":[]}\n'
            stderr = ""
        return P()

    out = ac._priority_sdk_repprep(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "url": "https://example.invalid",
            "user": "tabula",
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    argv = seen["argv"]
    joined = " ".join(str(a).replace("\\", "/") for a in argv)
    assert "run-repprep-via-exec.mjs" in joined
    assert "run-formprep-via-eform.mjs" not in joined
    assert "--proc" in argv
    assert argv[argv.index("--proc") + 1] == "FORMPREPDRCT2"


def test_fr6003_form_via_eform_opt_in_only(tmp_path, monkeypatch):
    """EFORM formprep runner is opt-in via AIRC_PRIORITY_FORM_VIA_EFORM=1."""
    root = tmp_path / "airc-install"
    pw_dir = root / "airc" / "priority-worker" / "sdk"
    pw_dir.mkdir(parents=True)
    (pw_dir / "run-repprep-via-exec.mjs").write_text("// stub repprep\n", encoding="utf-8")
    (pw_dir / "run-formprep-via-eform.mjs").write_text("// stub eform\n", encoding="utf-8")
    monkeypatch.setenv("AIRC_INSTALL_ROOT", str(root))
    monkeypatch.setenv("AIRC_PRIORITY_FORM_VIA_EFORM", "1")
    monkeypatch.setattr(
        ac._priority,
        "resolve_priority_worker_dir",
        lambda _r: root / "airc" / "priority-worker",
    )
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        class P:
            returncode = 0
            stdout = '{"ok":true,"ended":true,"errors":[]}\n'
            stderr = ""
        return P()

    out = ac._priority_sdk_repprep(
        ename="CUSTOMERS",
        path="FORMPREPDRCT2",
        form_prep=True,
        instance={
            "credentialTarget": "PriorityWeb/x",
            "company": "live1",
            "url": "https://example.invalid",
            "user": "api-user",
        },
        cred_fetcher=lambda _t: "secret-placeholder-priority-pw",
        node_runner=fake_run,
    )
    assert out.get("ok") is True
    joined = " ".join(str(a).replace("\\", "/") for a in seen["argv"])
    assert "run-formprep-via-eform.mjs" in joined
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
        return {"ok": True, "path": kw.get("path")}

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
