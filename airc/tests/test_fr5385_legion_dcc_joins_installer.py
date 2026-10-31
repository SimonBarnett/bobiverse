"""FR #5385: LEGION DCC log comes from installer_legion_work, not empty getattr."""
from __future__ import annotations

import json
import threading
import time

import airc_console as ac
import airc_legion as lg
from airc_auth_helpers import ops_auth


def test_fr5385_wait_attaches_status_and_failures():
    def work(target, **_kw):
        return {
            "ok": False,
            "target": target,
            "status": "winrm-fail",
            "error": "TimeoutError",
            "invoked_installer": True,
        }

    res = lg.run_legion_verb(target="box1", worker=work, wait=True, job_id="aabbccdd")
    assert res.status == "winrm-fail"
    assert res.failures[0]["error"] == "TimeoutError"
    log = lg.build_legion_log(
        target="box1", summary=res.status, failures=res.failures
    )
    assert log["failure_count"] == 1
    assert log["summary"] == "winrm-fail"


def test_fr5385_handler_delivers_after_accept_without_wait():
    sent: list[bytes] = []
    done = threading.Event()

    def send(payload: bytes, offer, **_k):
        sent.append(payload)
        done.set()

    def work(target, **_kw):
        return {
            "ok": True,
            "target": target,
            "status": "dry-run",
            "error": None,
            "invoked_installer": True,
        }

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        legion_runner=lambda **kw: lg.run_legion_verb(wait=False, **kw, worker=work),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.legion_log_send = send
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION box1 -WhatIf")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2
    assert hr and hr.action == "legion"
    assert "LEGION accepted" in (hr.reply or "")
    assert "failures=0" not in (hr.reply or "") or done.wait(0.01)
    assert done.wait(2.0)
    body = json.loads(sent[0].decode("utf-8"))
    assert body["target"] == "box1"
    assert body["summary"] == "dry-run"
