"""FR #5308: LEGION verb + isolated worker scaffold (no installer invoke)."""
from __future__ import annotations

import time

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5308_parse_single_host_or_ip():
    p = lg.parse_legion_command("LEGION walrus")
    assert p is not None and p.get("error") is None
    assert p["target"] == "walrus" and p["whatif"] is False
    ip = lg.parse_legion_command("id=aabbccdd LEGION 10.0.0.8 -WhatIf")
    assert ip["target"] == "10.0.0.8" and ip["whatif"] is True and ip["qid"] == "aabbccdd"
    assert lg.parse_legion_command("STATUS") is None
    assert lg.parse_legion_command("NETWORK") is None


def test_fr5308_refuse_empty_list_ou():
    assert lg.parse_legion_command("LEGION")["error"] == "empty"
    assert lg.parse_legion_command("LEGION  ")["error"] == "empty"
    assert lg.parse_legion_command("LEGION a,b")["error"] == "list"
    assert lg.parse_legion_command("LEGION host1 host2")["error"] == "list"
    assert lg.parse_legion_command("LEGION OU=Workstations")["error"] == "ou"
    assert lg.parse_legion_command("LEGION CN=x,DC=wonderland,DC=local")["error"] == "ou"


def test_fr5308_unauthorized_not_op():
    hr = _core().handle_raw(":evil!u@h PRIVMSG tm_console :LEGION walrus")
    assert hr is not None and hr.action == "deny"
    assert "126" in (hr.reply or "")


def test_fr5308_update_off_refuses():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :LEGION walrus")
    assert hr and hr.action == "capability_deny"
    assert "update-disabled" in (hr.reply or "")


def test_fr5308_bad_target_exit_126():
    hr = _core().handle_raw(":op!u@h PRIVMSG tm_console :LEGION a,b")
    assert hr and hr.action == "capability_deny"
    assert "126" in (hr.reply or "")
    assert "bad-target" in (hr.reply or "")


def test_fr5308_accepted_isolated_not_on_caller_thread():
    def slow_worker(**_kw):
        time.sleep(0.2)
        return {"ok": True, "invoked_installer": False}

    core = _core(legion_runner=lambda **kw: lg.run_legion_verb(worker=slow_worker, **kw))
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=c25bd00e LEGION walrus")
    elapsed = time.perf_counter() - t0
    assert hr and hr.action == "legion"
    assert "LEGION accepted" in (hr.reply or "")
    assert "DONE id=c25bd00e" not in (hr.reply or "")
    assert elapsed < 0.15
    assert "password=" not in (hr.reply or "").lower()
    assert "--force" not in (hr.reply or "").lower()


def test_fr5308_worker_fault_status_still_works(tmp_path):
    def boom(**_kw):
        raise RuntimeError("injected-legion-fault")

    proto = JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True)
    core = _core(
        job_protocol=proto,
        legion_runner=lambda **kw: lg.run_legion_verb(worker=boom, wait=True, **kw),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :LEGION walrus")
    assert hr and hr.action == "legion"
    assert proto.airc_running is True
    st = core.handle_raw(":op!u@h PRIVMSG tm_console :id=deadbeef STATUS")
    assert st and st.action == "job"
    help_hr = core.handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "LEGION" in (help_hr.reply or "")


def test_fr5308_stub_does_not_invoke_installer():
    body = lg.stub_legion_work("walrus", whatif=False)
    assert body.get("invoked_installer") is False
    assert body.get("force") is False
    assert body.get("timeout_s") == 900
