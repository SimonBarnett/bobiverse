"""MRB #5377 hostile pins for NETWORK DCC inventory+log (FR #5300)."""
from __future__ import annotations

import hashlib
import json

import airc_dcc_bulk as dcc
import airc_network as nw


def test_mrb5377_redacts_secret_keys_and_password_equals():
    payload = nw.build_network_payload(
        "diag",
        hosts=[{"hostname": "pc1", "ips": ["10.0.0.1"], "ou": "OU=PCs"}],
        failures=[{"host": "pc2", "error": "OSError"}],
        extra={"password": "x", "api_token": "y", "note": "ok"},
    )
    blob = json.dumps(payload)
    assert "password" not in blob.lower()
    assert "api_token" not in blob.lower()
    assert payload["note"] == "ok"
    assert payload["host_count"] == 1
    assert payload["failure_count"] == 1
    assert "password=" not in blob.lower()


def test_mrb5377_dcc_sha_and_cont_fallback():
    payload = nw.build_network_payload(
        "diag",
        hosts=[{"hostname": "pc1", "ips": [], "ou": "unknown"}],
        failures=[],
    )
    raw = nw.network_payload_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    sent: list[bytes] = []

    def send(body: bytes, offer, **_k):
        sent.append(body)

    offer = dcc.DccListenOffer("aabbccdd", "127.0.0.1", 9, "ab" * 16, tls=False)
    out = nw.deliver_network_payload(
        job_id="aabbccdd", payload=payload, offer=offer, send_fn=send
    )
    assert out["via"] == "dcc"
    assert digest in out["done"]
    assert sent[0] == raw
    none = nw.deliver_network_payload(job_id="aabbccdd", payload=payload, offer=None)
    assert none["via"] == "irc"
    assert "CONT" in "\n".join(none["lines"])


def test_mrb5377_no_invented_hosts_in_payload():
    payload = nw.build_network_payload("diag", hosts=[], failures=[])
    assert payload["hosts"] == []
    assert payload["host_count"] == 0
    inv = nw.inventory_work(
        ldap_enum=lambda: [{"hostname": "only-ad", "dn": "CN=only-ad,OU=Lab,DC=ex"}],
        resolve_ips=lambda _h: ["10.1.2.3"],
        extra_hosts=["rogue.example"],
    )
    assert [h["hostname"] for h in inv["hosts"]] == ["only-ad"]
    assert "rogue" not in json.dumps(inv)
