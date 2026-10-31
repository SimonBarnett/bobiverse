"""FR #5311: LEGION installer log via DCCLISTEN or IRC CONT; no secrets."""
from __future__ import annotations

import hashlib
import json

import airc_console as ac
import airc_dcc_bulk as dcc
import airc_legion as lg
from airc_auth_helpers import ops_auth


def _log(**kw):
    return lg.build_legion_log(
        target=kw.get("target", "walrus"),
        whatif=kw.get("whatif", False),
        summary=kw.get("summary", "dry-run"),
        failures=kw.get("failures", [{"host": "walrus", "error": "timeout"}]),
        extra=kw.get("extra"),
    )


def test_fr5311_payload_has_failures_and_redacts():
    log = _log(extra={"password": "nope", "token": "abc"})
    blob = json.dumps(log).lower()
    assert "password" not in blob
    assert "nope" not in blob
    assert log["failures"]
    assert log["failure_count"] == len(log["failures"])
    assert log["target"] == "walrus"
    raw = lg.legion_log_bytes(log)
    assert hashlib.sha256(raw).hexdigest() == dcc.sha256_hex(raw)


def test_fr5311_dcc_when_offer_sha_matches():
    captured: list[bytes] = []

    def send(payload: bytes, offer, **_k):
        captured.append(payload)

    log = _log()
    offer = dcc.DccListenOffer("aabbccdd", "127.0.0.1", 9, "ab" * 16, tls=False)
    out = lg.deliver_legion_log(
        job_id="aabbccdd", log=log, offer=offer, send_fn=send
    )
    assert out["via"] == "dcc"
    assert "via=dcc" in out["done"]
    assert captured
    assert dcc.sha256_hex(captured[0]) in out["done"]
    body = json.loads(captured[0].decode("utf-8"))
    assert body["failures"]
    assert "failures=" in out["summary"]
    assert "password=" not in captured[0].decode("utf-8").lower()


def test_fr5311_no_offer_uses_cont():
    out = lg.deliver_legion_log(job_id="c25bd00e", log=_log(), offer=None)
    assert out["via"] == "irc"
    assert "CONT" in "\n".join(out["lines"])
    assert "via=dcc" not in out["done"]


def test_fr5311_dcc_fail_falls_back():
    def boom(payload, offer, **_k):
        raise OSError("refused")

    offer = dcc.DccListenOffer("deadbeef", "127.0.0.1", 1, "cd" * 16)
    out = lg.deliver_legion_log(
        job_id="deadbeef", log=_log(), offer=offer, send_fn=boom
    )
    assert out["via"] == "irc"
    assert "dcc-fail" in out["done"] or "dcc failed" in "\n".join(out["lines"]).lower()


def test_fr5311_console_wires_dcclisten():
    sent: list[bytes] = []

    def send(payload: bytes, offer, **_k):
        sent.append(payload)

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.legion_log_send = send
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd LEGION walrus -WhatIf")
    assert hr is not None and hr.action == "legion"
    assert "via=dcc" in (hr.reply or "")
    assert "failures=" in (hr.reply or "")
    assert sent
    assert "password=" not in (hr.reply or "").lower()
    assert "password=" not in sent[0].decode("utf-8").lower()
