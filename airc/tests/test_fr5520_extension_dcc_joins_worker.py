"""FR #5520: EXTENSION DCC log comes from the worker payload, not accept defaults."""
from __future__ import annotations

import json
import threading
import time

import airc_console as ac
import airc_extension as ex
from airc_auth_helpers import ops_auth


def test_fr5520_wait_attaches_payload_hosts_and_gpo():
    def work(**_kw):
        return {
            "ok": True,
            "gpo": "present",
            "gpo_detail": {
                "ok": True,
                "gpo": "present",
                "gpo_name": ex.DEFAULT_GPO_NAME,
                "browsers": ["chrome", "edge"],
                "policy_names": [ex.DEFAULT_GPO_NAME],
                "wrote_gpo": False,
            },
            "hosts": [
                {"host": "PC1", "ok": True, "would_write": True},
                {"host": "PC2", "ok": False, "error": "unreachable"},
            ],
            "wrote_gpo": False,
            "browsers": ["chrome", "edge"],
        }

    res = ex.run_extension_verb(action="install", worker=work, wait=True, job_id="aabbccdd")
    assert res.payload is not None
    assert len(res.payload.get("hosts") or []) == 2
    log = ex.extension_log_from_payload("install", whatif=True, payload=res.payload)
    assert log["gpo"]["attempted"] is True
    assert log["gpo"]["result"] == "present"
    assert log["fallback"]["attempted"] is True
    assert len(log["hosts"]) == 2
    assert "not-implemented-fr-b" not in json.dumps(log)


def test_fr5520_handler_delivers_after_accept_without_wait():
    sent: list[bytes] = []
    done = threading.Event()

    def send(payload: bytes, offer, **_k):
        sent.append(payload)
        done.set()

    def work(**_kw):
        return {
            "ok": True,
            "gpo": "present",
            "gpo_detail": {
                "ok": True,
                "gpo": "present",
                "gpo_name": ex.DEFAULT_GPO_NAME,
                "browsers": ["chrome", "edge"],
                "policy_names": [ex.DEFAULT_GPO_NAME],
                "wrote_gpo": False,
            },
            "hosts": [
                {"host": "ADPC1", "ok": True, "would_write": True},
                {"host": "ADPC2", "ok": False, "error": "unreachable"},
            ],
            "wrote_gpo": False,
            "browsers": ["chrome", "edge"],
        }

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        extension_runner=lambda **kw: ex.run_extension_verb(wait=False, **kw, worker=work),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.extension_log_send = send
    t0 = time.perf_counter()
    hr = core.handle_raw(
        ":op!u@h PRIVMSG tm_console :id=aabbccdd EXTENSION install -WhatIf"
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2
    assert hr and hr.action == "extension"
    assert "EXTENSION accepted" in (hr.reply or "")
    assert done.wait(2.0)
    body = json.loads(sent[0].decode("utf-8"))
    assert body["action"] == "install"
    assert body["whatif"] is True
    assert body["gpo"]["attempted"] is True
    assert body["gpo"]["result"] == "present"
    assert body["fallback"]["attempted"] is True
    assert len(body["hosts"]) == 2
    assert "not-implemented-fr-b" not in json.dumps(body)


def test_fr5520_empty_accept_payload_keeps_stub_failure_only_without_worker_result():
    log = ex.build_extension_log("install", whatif=True)
    assert log["failures"][0]["error"] == "not-implemented-fr-b"
    log2 = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={
            "ok": True,
            "gpo": "ok",
            "gpo_detail": {"ok": True, "gpo": "ok", "wrote_gpo": True},
            "hosts": [],
        },
    )
    assert log2["gpo"]["attempted"] is True
    assert log2["failures"] == [] or "not-implemented-fr-b" not in json.dumps(log2)
