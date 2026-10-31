"""FR #5379: NETWORK DCC payload comes from inventory_work, not empty getattr."""
from __future__ import annotations

import json
import threading
import time

import airc_console as ac
import airc_network as nw
from airc_auth_helpers import ops_auth


def test_fr5379_wait_attaches_hosts_on_result():
    def work(**_kw):
        return {
            "ok": True,
            "hosts": [{"hostname": "pc1", "ips": ["10.0.0.1"], "ou": "OU=PCs"}],
            "log": [{"host": "pc2", "error": "OSError", "step": "resolve"}],
        }

    res = nw.run_network_verb(worker=work, wait=True, job_id="aabbccdd")
    assert res.hosts[0]["hostname"] == "pc1"
    assert res.failures[0]["host"] == "pc2"
    payload = nw.build_network_payload(
        "diag", hosts=res.hosts, failures=res.failures
    )
    assert payload["host_count"] == 1
    assert payload["failure_count"] == 1


def test_fr5379_handler_delivers_after_accept_without_wait(monkeypatch):
    sent: list[bytes] = []
    done = threading.Event()

    def send(payload: bytes, offer, **_k):
        sent.append(payload)
        done.set()

    def work(**_kw):
        return {
            "ok": True,
            "hosts": [{"hostname": "only-ad", "ips": ["10.1.2.3"], "ou": "OU=Lab"}],
            "log": [],
        }

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        network_runner=lambda **kw: nw.run_network_verb(worker=work, wait=False, **kw),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.network_log_send = send
    t0 = time.perf_counter()
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2
    assert hr and hr.action == "network"
    assert "NETWORK accepted" in (hr.reply or "")
    assert "hosts=0" not in (hr.reply or "")
    assert done.wait(2.0)
    body = json.loads(sent[0].decode("utf-8"))
    assert [h["hostname"] for h in body["hosts"]] == ["only-ad"]
    assert body["host_count"] == 1
