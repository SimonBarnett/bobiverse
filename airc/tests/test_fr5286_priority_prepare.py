"""FR #5286: PRIORITY prepare — EXEC REPPREPDIRECT2 + UPD=N + .prp mtime."""
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
