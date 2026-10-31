"""FR #5286: PRIORITY prepare - EXEC REPPREPDIRECT2 + UPD=N + .prp mtime."""
from __future__ import annotations

import json
import sys

from unittest.mock import MagicMock

import airc_console as ac
from airc_auth_helpers import ops_auth
from repo_layout import ROOT

_WP = ROOT / "airc" / "priority-worker"
if str(_WP) not in sys.path:
    sys.path.insert(0, str(_WP))

import priority_worker as pw  # noqa: E402


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
    }
    h.update(over)
    return h


def test_fr5286_name_missing_and_no_cred():
    r = pw.run_priority_prepare("", instance_id="example-dev", instances=[INST], **_ok_hooks())
    assert r["reason"] == "name_missing"
    assert r["ok"] is False
    r2 = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(cred_present=lambda t: False),
    )
    assert r2["reason"] == "no_cred"
    assert r2["ok"] is False
    blob = json.dumps(r2).lower()
    assert "password=" not in blob
    assert "secret" not in blob


def test_fr5286_success_requires_ok_upd_n_prp_advance():
    r = pw.run_priority_prepare("FOO", instance_id="example-dev", instances=[INST], **_ok_hooks())
    assert r["ok"] is True
    assert r["reason"] == "prepared"
    assert r["exec"] == "REPPREPDIRECT2"
    assert r["upd"] == "N"
    assert r["prp_advanced"] is True
    assert r.get("sql_faked") is False

    still = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(read_upd=lambda **kw: "Y"),
    )
    assert still["ok"] is False
    assert still["reason"] == "still_unprepared"

    stale = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(prp_mtime_after=lambda **kw: 1000.0),
    )
    assert stale["ok"] is False
    assert stale["reason"] == "prp_unchanged"

    toast = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(sdk_exec=lambda **kw: {"ok": False, "path": "REPPREPDIRECT2"}),
    )
    assert toast["ok"] is False
    assert toast["reason"] in {"sdk_not_ok", "still_unprepared"}


def test_fr5286_type_p_never_form_prep():
    seen = {}

    def sdk_exec(**kw):
        seen.update(kw)
        return {"ok": True, "path": "REPPREPDIRECT2"}

    r = pw.run_priority_prepare(
        "FOO",
        instance_id="example-dev",
        instances=[INST],
        **_ok_hooks(sdk_exec=sdk_exec, proc_type="P"),
    )
    assert r["ok"] is True
    assert seen.get("path") == "REPPREPDIRECT2"
    assert seen.get("form_prep") is not True
    assert "FORM" not in str(seen.get("path", "")).upper() or seen.get("path") == "REPPREPDIRECT2"


def test_fr5286_console_prepare_framing_no_password():
    auth = ops_auth("op")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=MagicMock(),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=c25bd00e PRIORITY prepare FOO instance=example-dev")
    assert hr is not None
    assert hr.action == "priority"
    text = (hr.reply or "") + " " + (hr.text or "")
    assert "password=" not in text.lower()
    # help mentions PRIORITY prepare
    help_hr = core.handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "PRIORITY" in (help_hr.reply or "")
    assert "prepare" in (help_hr.reply or "").lower()


def test_fr5286_skills_document_prepare_gates():
    cmd = (ROOT / "airc/.grok/skills/bobiverse-airc-commands/SKILL.md").read_text(encoding="utf-8")
    assert "PRIORITY prepare" in cmd
    assert "REPPREPDIRECT2" in cmd
    assert "EXECPREPLOCK" in cmd or "UPD" in cmd
    assert ".prp" in cmd
    assert "password=" not in cmd.lower()
    assert "\u2014" not in cmd


def test_fr5286_default_hooks_wire_cred_upd_prp():
    """Live-style hooks: CredMan + lock UPD + .prp advance (injectable)."""
    seen = {"cred": 0, "lock": 0, "sdk": 0}

    def fetcher(target: str) -> str:
        seen["cred"] += 1
        assert target == "PriorityWeb/example-dev"
        # FAKE_ placeholder - never a real secret (FR #3304).
        return "FAKE_" + "PREPARE_SECRET"

    def lock_reader(*, ename, instance, exec_type="P"):
        seen["lock"] += 1
        return {"name": ename, "exec_id": 42, "exec_type": exec_type, "upd": "N"}

    def sdk_exec(**kw):
        seen["sdk"] += 1
        assert kw.get("path") == "REPPREPDIRECT2"
        assert kw.get("form_prep") is False
        return {"ok": True, "path": "REPPREPDIRECT2"}

    mt = {"n": 0}

    def prp_stat(**kw):
        mt["n"] += 1
        # first call before, second after - advance
        return 1000.0 if mt["n"] == 1 else 1001.0

    hooks = pw.build_default_prepare_hooks(
        cred_fetcher=fetcher,
        lock_reader=lock_reader,
        sdk_exec=sdk_exec,
        prp_stat=prp_stat,
    )
    r = pw.run_priority_prepare(
        "FOO", instance_id="example-dev", instances=[INST], **hooks
    )
    assert r["ok"] is True
    assert r["reason"] == "prepared"
    assert r["upd"] == "N"
    assert r["prp_advanced"] is True
    assert seen["cred"] >= 1
    assert seen["sdk"] == 1
    assert seen["lock"] >= 1


def test_fr5286_parse_positional_after_instance_kv():
    d = ac.parse_priority_prepare_command("PRIORITY prepare instance=example-dev FOO")
    assert d is not None
    assert d["name"] == "FOO"
    assert d["instance"] == "example-dev"


def test_fr5286_console_prepare_uses_hooks_not_bare_no_cred(monkeypatch, tmp_path):
    """Console must supply default hooks so success path is reachable under injectables."""
    auth = ops_auth("op")
    calls = {"hooks": 0}

    def fake_hooks(install_root=None):
        calls["hooks"] += 1
        return pw.build_default_prepare_hooks(
            cred_fetcher=lambda t: "FAKE_" + "X",
            lock_reader=lambda **k: {
                "name": k.get("ename"),
                "exec_id": 7,
                "exec_type": "P",
                "upd": "N",
            },
            sdk_exec=lambda **k: {"ok": True, "path": "REPPREPDIRECT2"},
            prp_stat=lambda **k: 2.0 if calls.setdefault("prp", 0) or True else 1.0,
        )

    # prp_stat needs before < after - use counter
    state = {"n": 0}

    def fake_hooks2(install_root=None):
        calls["hooks"] += 1

        def prp_stat(**k):
            state["n"] += 1
            return 10.0 if state["n"] == 1 else 11.0

        return pw.build_default_prepare_hooks(
            cred_fetcher=lambda t: "FAKE_" + "X",
            lock_reader=lambda **k: {
                "name": k.get("ename"),
                "exec_id": 7,
                "exec_type": "P",
                "upd": "N",
            },
            sdk_exec=lambda **k: {"ok": True, "path": "REPPREPDIRECT2"},
            prp_stat=prp_stat,
        )

    monkeypatch.setattr(ac, "build_console_prepare_hooks", fake_hooks2)
    monkeypatch.setattr(
        ac,
        "load_priority_instances",
        lambda root=None: [INST],
    )
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        sessions=ac.ConsoleSessionManager(on_output=None),
        nick="tm_console",
        job_protocol=MagicMock(),
        install_root=str(tmp_path),
    )
    hr = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=c25bd00e PRIORITY prepare FOO instance=example-dev"
    )
    assert hr is not None
    assert hr.action == "priority"
    assert calls["hooks"] >= 1
    assert '"ok":true' in (hr.reply or "").replace(" ", "") or '"reason":"prepared"' in (
        hr.reply or ""
    )
    assert "password=" not in (hr.reply or "").lower()
    assert "FAKE_" not in (hr.reply or "")
