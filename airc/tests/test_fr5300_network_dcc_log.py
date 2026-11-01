"""FR #5300: NETWORK inventory+log via DCCLISTEN or IRC CONT; no secrets."""
from __future__ import annotations

import hashlib
import json
import threading

import airc_console as ac
import airc_dcc_bulk as dcc
import airc_network as nw
from airc_auth_helpers import ops_auth


def _payload(**kw):
    return nw.build_network_payload(
        "diag",
        hosts=kw.get(
            "hosts",
            [{"hostname": "pc1", "ips": ["10.0.0.1"], "ou": "OU=PCs,DC=ex", "dn": "CN=pc1,OU=PCs,DC=ex"}],
        ),
        failures=kw.get("failures", [{"host": "pc2", "error": "OSError", "step": "resolve"}]),
        extra=kw.get("extra"),
    )


def test_fr5300_payload_has_hosts_failures_and_redacts():
    log = _payload(extra={"password": "nope", "token": "abc"})
    blob = json.dumps(log).lower()
    assert "password" not in blob
    assert "nope" not in blob
    assert log["hosts"]
    assert log["failures"]
    assert log["host_count"] == len(log["hosts"])
    assert log["failure_count"] == len(log["failures"])
    raw = nw.network_payload_bytes(log)
    assert hashlib.sha256(raw).hexdigest() == dcc.sha256_hex(raw)


def test_fr5300_dcc_when_offer_sha_matches():
    captured: list[bytes] = []

    def send(payload: bytes, offer, **_k):
        captured.append(payload)

    log = _payload()
    offer = dcc.DccListenOffer("aabbccdd", "127.0.0.1", 9, "ab" * 16, tls=False)
    out = nw.deliver_network_payload(
        job_id="aabbccdd", payload=log, offer=offer, send_fn=send
    )
    assert out["via"] == "dcc"
    assert "via=dcc" in out["done"]
    assert captured
    assert dcc.sha256_hex(captured[0]) in out["done"]
    body = json.loads(captured[0].decode("utf-8"))
    assert body["hosts"] and body["failures"]
    assert "hosts=" in out["summary"] and "failures=" in out["summary"]
    assert "password=" not in captured[0].decode("utf-8").lower()
    assert "password=" not in out["done"].lower()


def test_fr5300_no_offer_uses_cont_pages():
    log = _payload()
    out = nw.deliver_network_payload(job_id="c25bd00e", payload=log, offer=None)
    assert out["via"] == "irc"
    text = "\n".join(out["lines"])
    assert "CONT" in text
    assert "hosts=" in out["summary"]
    assert "via=dcc" not in out["done"]
    assert "DONE id=c25bd00e" in out["done"]


def test_fr5300_dcc_fail_falls_back_to_irc():
    def boom(payload, offer, **_k):
        raise OSError("refused")

    log = _payload()
    offer = dcc.DccListenOffer("deadbeef", "127.0.0.1", 1, "cd" * 16)
    out = nw.deliver_network_payload(
        job_id="deadbeef", payload=log, offer=offer, send_fn=boom
    )
    assert out["via"] == "irc"
    assert "dcc-fail" in out["done"] or "dcc failed" in "\n".join(out["lines"]).lower()


def test_fr5300_console_wires_dcclisten_same_job_id():
    """DCCLISTEN same job id is taken and passed to network_log_send.

    FR #5575: do not wait on packaged inventory_work (real LDAP/AD). A host
    with a live domain can exceed any fixed wait and never call send. Stub a
    fast worker (same pattern as FR #5379) so this pin stays deterministic.
    """
    sent: list[tuple[bytes, object]] = []
    done = threading.Event()

    def send(payload: bytes, offer, **_k):
        sent.append((payload, offer))
        done.set()

    def work(**_kw):
        return {
            "ok": True,
            "hosts": [
                {
                    "hostname": "pc1",
                    "ips": ["10.0.0.1"],
                    "ou": "OU=PCs,DC=ex",
                    "dn": "CN=pc1,OU=PCs,DC=ex",
                }
            ],
            "log": [{"host": "pc2", "error": "OSError", "step": "resolve"}],
        }

    auth = ops_auth("op", channel="#tm")
    core = ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=ac.ShellJobRunner(on_reply=lambda *_a, **_k: None),
        network_runner=lambda **kw: nw.run_network_verb(
            worker=work, wait=False, **kw
        ),
    )
    core.shell_runner.note_dcclisten(
        "DCCLISTEN id=aabbccdd host=127.0.0.1 port=9 token=" + ("ab" * 16) + " tls=0"
    )
    core.network_log_send = send
    hr = core.handle_raw(":op!u@h PRIVMSG tm_console :id=aabbccdd NETWORK diag")
    assert hr is not None and hr.action == "network"
    assert "NETWORK accepted" in (hr.reply or "")
    assert done.wait(2.0), "network_log_send never ran"
    assert sent
    payload, offer = sent[0]
    assert offer is not None
    assert getattr(offer, "job_id", None) == "aabbccdd"
    # Same-job take consumed the offer.
    assert core.shell_runner.take_dcclisten("aabbccdd") is None
    body = json.loads(payload.decode("utf-8"))
    assert "hosts" in body and "failures" in body
    assert body["hosts"][0]["hostname"] == "pc1"
    assert "password=" not in (hr.reply or "").lower()
    assert "password=" not in payload.decode("utf-8").lower()
