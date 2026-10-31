"""FR #5298: NETWORK / NETWORK diag isolated worker scaffold (no LDAP)."""
from __future__ import annotations

import time

import airc_console as ac
import airc_network as nw
from airc_auth_helpers import ops_auth
from airc_jobs import JobProtocol, JobStore


def _core(**kw):
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(machine="tm", auth=auth, nick="tm_console", **kw)


def test_fr5298_parse_network_and_diag():
    assert nw.parse_network_command("NETWORK")["action"] == "diag"
    assert nw.parse_network_command("NETWORK diag")["action"] == "diag"
    w = nw.parse_network_command("id=aabbccdd NETWORK diag -WhatIf")
    assert w["whatif"] is True and w["qid"] == "aabbccdd"
    assert nw.parse_network_command("STATUS") is None
    assert nw.parse_network_command("NETWORK sweep") is None


def test_fr5298_unauthorized_not_op():
    hr = _core().handle_raw(":evil!u@h PRIVMSG tm_console :NETWORK diag")
    assert hr is not None and hr.action == "deny"
    assert "126" in (hr.reply or "")


def test_fr5298_update_off_refuses():
    core = _core(capabilities=ac.ConsoleCapabilities(update="off"))
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :NETWORK")
    assert hr and hr.action == "capability_deny"
    assert "update-disabled" in (hr.reply or "")


def test_fr5298_accepted_isolated_not_on_caller_thread():
    def slow_worker(**_kw):
        time.sleep(0.2)
        return {"ok": True, "ldap": False}

    core = _core(network_runner=lambda **kw: nw.run_network_verb(worker=slow_worker, **kw))
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=c25bd00e NETWORK diag")
    elapsed = time.perf_counter() - t0
    assert hr and hr.action == "network"
    assert "NETWORK accepted" in (hr.reply or "")
    assert "DONE id=c25bd00e exit=0" in (hr.reply or "")
    assert elapsed < 0.15
    assert "password=" not in (hr.reply or "").lower()


def test_fr5298_worker_fault_status_still_works(tmp_path):
    def boom(**_kw):
        raise RuntimeError("injected-network-fault")

    proto = JobProtocol(JobStore(tmp_path / "home"), machine="tm", airc_running=True)
    core = _core(
        job_protocol=proto,
        network_runner=lambda **kw: nw.run_network_verb(worker=boom, wait=True, **kw),
    )
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :NETWORK")
    assert hr and hr.action == "network"
    assert proto.airc_running is True
    st = core.handle_raw(":op!u@h PRIVMSG tm_console :id=deadbeef STATUS")
    assert st and st.action == "job"
    help_hr = core.handle_raw(":op!u@h PRIVMSG tm_console :!help")
    assert "NETWORK" in (help_hr.reply or "")
