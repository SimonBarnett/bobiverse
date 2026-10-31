"""FR #5290: EXTENSION verb + isolated worker scaffold (no GPO in this slice)."""
from __future__ import annotations

import threading
import time

import airc_console as ac
import airc_extension as ex
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5290_parse_install_status_whatif():
    assert ex.DEFAULT_EXTENSION_ID == "cgmpadejahkaggjpffnhaoiafbnicgpa"
    p = ex.parse_extension_command("EXTENSION install")
    assert p is not None and p["action"] == "install" and p["whatif"] is False
    w = ex.parse_extension_command("id=aabbccdd EXTENSION install -WhatIf")
    assert w["whatif"] is True and w["qid"] == "aabbccdd"
    s = ex.parse_extension_command("EXTENSION status")
    assert s["action"] == "status"
    assert ex.parse_extension_command("STATUS") is None


def test_fr5290_stub_worker_never_mutates_gpo():
    body = ex.stub_extension_work("install", whatif=False)
    assert body.get("wrote_gpo") is False
    assert body.get("wrote_registry") is False
    assert body["extension_id"] == ex.DEFAULT_EXTENSION_ID


def test_fr5290_unauthorized_not_op():
    core = _core()
    hr = core.handle_raw(":evil!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None and hr.action == "deny"
    assert "126" in (hr.reply or "") or "not-op" in (hr.reply or "").lower()


def test_fr5290_update_off_refuses():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None
    assert hr.action == "capability_deny"
    assert "update-disabled" in (hr.reply or "")


def test_fr5290_accepted_and_isolated_not_on_caller_thread():
    marker = {"in_worker": False}

    def slow_worker(**_kw):
        marker["in_worker"] = threading.current_thread() is not threading.main_thread()
        time.sleep(0.2)
        return {"ok": True, "wrote_gpo": False}

    core = _core(extension_runner=lambda **kw: ex.run_extension_verb(worker=slow_worker, **kw))
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=c25bd00e EXTENSION install")
    elapsed = time.perf_counter() - t0
    assert hr is not None and hr.action == "extension"
    assert "EXTENSION accepted" in (hr.reply or "") or "accepted" in (hr.reply or "").lower()
    assert elapsed < 0.15
    assert "password=" not in (hr.reply or "").lower()


def test_fr5290_worker_fault_console_still_handles_status(tmp_path):
    def boom(**_kw):
        raise RuntimeError("injected-extension-fault")

    proto = JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True)
    core = _core(
        job_protocol=proto,
        extension_runner=lambda **kw: ex.run_extension_verb(worker=boom, wait=True, **kw),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :EXTENSION install")
    assert hr is not None
    assert hr.action == "extension"
    assert proto.airc_running is True
    st = core.handle_raw(":op!u@h PRIVMSG tm_console :id=deadbeef STATUS")
    assert st is not None
    assert st.action == "job"
    help_hr = core.handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "EXTENSION" in (help_hr.reply or "")
