"""FR #5293: EXTENSION structured log via DCCLISTEN or IRC CONT; no secrets."""
from __future__ import annotations

import hashlib
import json

import airc_console as ac
import airc_dcc_bulk as dcc
import airc_extension as ex
from airc_auth_helpers import ops_auth


def test_fr5293_log_schema_redacts_and_lists_failures():
    log = ex.build_extension_log(
        "install",
        whatif=True,
        hosts=[{"hostname": "pc1", "ok": False, "error": "access-denied"}],
        failures=[{"step": "fallback", "host": "pc1", "error": "access-denied"}],
        extra={"password": "nope", "token": "abc"},
    )
    blob = json.dumps(log).lower()
    assert "password" not in blob
    assert "nope" not in blob
    assert log["failure_count"] >= 1
    assert log["failures"]
    assert "gpo" in log and "fallback" in log
    raw = ex.extension_log_bytes(log)
    assert hashlib.sha256(raw).hexdigest() == dcc.sha256_hex(raw)


def test_fr5293_dcc_when_offer_sha_matches():
    captured: list[bytes] = []

    def send(payload: bytes, offer, **_k):
        captured.append(payload)

    log = ex.build_extension_log("install", failures=[{"step": "gpo", "error": "stub"}])
    offer = dcc.DccListenOffer("aabbccdd", "127.0.0.1", 9, "ab" * 16, tls=False)
    out = ex.deliver_extension_log(
        job_id="aabbccdd", log=log, offer=offer, send_fn=send
    )
    assert out["via"] == "dcc"
    assert "via=dcc" in out["done"]
    assert captured
    assert dcc.sha256_hex(captured[0]) in out["done"]
    assert "failures=" in out["summary"]
    assert "password=" not in out["done"].lower()


def test_fr5293_no_offer_uses_cont_pages():
    log = ex.build_extension_log(
        "install",
        failures=[{"step": "gpo", "error": "not-implemented-fr-b"}],
    )
    out = ex.deliver_extension_log(job_id="c25bd00e", log=log, offer=None)
    assert out["via"] == "irc"
    text = "\n".join(out["lines"])
    assert "CONT" in text or "failure" in text.lower()
    assert "not-implemented-fr-b" in text
    assert "via=dcc" not in out["done"]
    assert "DONE id=c25bd00e" in out["done"]


def test_fr5293_dcc_fail_falls_back_to_irc():
    def boom(payload, offer, **_k):
        raise OSError("refused")

    log = ex.build_extension_log("install", failures=[{"step": "gpo", "error": "x"}])
    offer = dcc.DccListenOffer("deadbeef", "127.0.0.1", 1, "cd" * 16)
    out = ex.deliver_extension_log(
        job_id="deadbeef", log=log, offer=offer, send_fn=boom
    )
    assert out["via"] == "irc"
    assert "dcc-fail" in out["done"] or "dcc failed" in "\n".join(out["lines"]).lower()


def test_fr5293_console_wires_same_job_id():
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
    # inject send
    core.extension_log_send = send
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd EXTENSION install")
    assert hr is not None and hr.action == "extension"
    assert "failures=" in (hr.reply or "")
    assert "password=" not in (hr.reply or "").lower()
