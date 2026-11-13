"""FR #7129: PUT via=dcc always DONE; fail-closed without IRC CHUNK."""
from __future__ import annotations

import hashlib

import airc_jobs as jobs


def test_dcc_put_success_emits_done(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    payload = b"ok-body"
    digest = hashlib.sha256(payload).hexdigest()

    def recv(_jid: str):
        return payload, digest

    proto.dcc_receive = recv
    lines = proto.handle(
        "bob-tm",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "ok.bin",
            "bytes": str(len(payload)),
            "sha256": digest,
            "via": "dcc",
        },
    )
    assert any(ln.startswith("DONE id=aabbccdd exit=0") for ln in lines)
    assert any("via=dcc" in ln for ln in lines)


def test_dcc_put_without_listener_fail_closed(tmp_path):
    store = jobs.JobStore(tmp_path)
    proto = jobs.JobProtocol(store)
    digest = hashlib.sha256(b"x").hexdigest()
    lines = proto.handle(
        "bob-tm",
        "PUT",
        {
            "id": "aabbccdd",
            "path": "x.bin",
            "bytes": "1",
            "sha256": digest,
            "via": "dcc",
        },
    )
    assert any("code=dcc-unreachable" in ln for ln in lines)
    assert any(ln.startswith("DONE id=aabbccdd exit=1") for ln in lines)
    joined = "\n".join(lines)
    assert "falling back to IRC" not in joined
    assert not (tmp_path / "drop" / "x.bin").exists()
