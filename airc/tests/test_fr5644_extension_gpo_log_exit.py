"""FR #5644: EXTENSION GPO log keeps error/dc/gpo_via, failures[] includes GPO, DONE exit!=0."""
from __future__ import annotations

import json

import airc_dcc_bulk as dcc
import airc_extension as ex


def test_fr5644_format_gpo_log_keeps_error_dc_gpo_via():
    raw = {
        "ok": False,
        "gpo": "fail",
        "gpo_name": ex.DEFAULT_GPO_NAME,
        "reason": "gpo_remote_failed",
        "wrote_gpo": False,
        "browsers": ["chrome", "edge"],
        "policy_names": [ex.DEFAULT_GPO_NAME],
        "error": "Connecting to remote server WALRUS.wonderland.local failed: Access is denied.",
        "dc": "WALRUS.wonderland.local",
        "gpo_via": "invoke_command_dc",
    }
    block = ex._format_gpo_log_block(raw)
    assert block["reason"] == "gpo_remote_failed"
    assert block["ok"] is False
    assert "Access is denied" in (block.get("error") or "")
    assert block.get("dc") == "WALRUS.wonderland.local"
    assert block.get("gpo_via") == "invoke_command_dc"
    # Still no secrets.
    blob = json.dumps(block).lower()
    assert "password" not in blob


def test_fr5644_extension_log_includes_gpo_failure_step():
    payload = {
        "ok": True,  # fill-holes partial success must not hide GPO fail
        "gpo": "fail",
        "gpo_reason": "gpo_remote_failed",
        "gpo_detail": {
            "ok": False,
            "gpo": "fail",
            "reason": "gpo_remote_failed",
            "wrote_gpo": False,
            "browsers": ["chrome", "edge"],
            "policy_names": [ex.DEFAULT_GPO_NAME],
            "error": "Access is denied.",
            "dc": "WALRUS.wonderland.local",
            "gpo_via": "invoke_command_dc",
        },
        "hosts": [
            {"host": "REDQUEEN", "ok": False, "error": "unreachable"},
            {"host": "PC2", "ok": False, "error": "unreachable"},
            {"host": "PC3", "ok": False, "error": "unreachable"},
        ],
        "wrote_gpo": False,
    }
    log = ex.extension_log_from_payload("install", whatif=False, payload=payload)
    assert log["gpo"]["ok"] is False
    assert "Access is denied" in (log["gpo"].get("error") or "")
    assert log["gpo"].get("dc") == "WALRUS.wonderland.local"
    assert log["gpo"].get("gpo_via") == "invoke_command_dc"
    gpo_fails = [f for f in log["failures"] if f.get("step") == "gpo"]
    assert len(gpo_fails) == 1
    assert "Access is denied" in (gpo_fails[0].get("error") or "")
    assert gpo_fails[0].get("dc") == "WALRUS.wonderland.local"
    assert log["failure_count"] >= 4  # 1 gpo + 3 hosts


def test_fr5644_deliver_done_exit_nonzero_when_failures():
    log = ex.extension_log_from_payload(
        "install",
        whatif=False,
        payload={
            "ok": False,
            "gpo": "fail",
            "gpo_detail": {
                "ok": False,
                "gpo": "fail",
                "reason": "gpo_remote_failed",
                "error": "Access is denied.",
                "dc": "WALRUS.wonderland.local",
                "gpo_via": "invoke_command_dc",
                "wrote_gpo": False,
            },
            "hosts": [
                {"host": "H1", "ok": False, "error": "unreachable"},
            ],
        },
    )
    assert log["failure_count"] >= 2
    offer = dcc.DccListenOffer("e3000001", "127.0.0.1", 9, "ab" * 16, tls=False)
    sent: list[bytes] = []

    def send(payload: bytes, offer, **_k):
        sent.append(payload)

    out = ex.deliver_extension_log(
        job_id="e3000001", log=log, offer=offer, send_fn=send
    )
    assert "exit=0" not in out["done"]
    assert "exit=1" in out["done"]
    assert sent


def test_fr5644_deliver_done_exit_zero_when_clean():
    log = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={
            "ok": True,
            "gpo": "present",
            "gpo_detail": {
                "ok": True,
                "gpo": "present",
                "wrote_gpo": False,
                "browsers": ["chrome"],
                "policy_names": [ex.DEFAULT_GPO_NAME],
            },
            "hosts": [{"host": "H1", "ok": True, "would_write": True}],
        },
    )
    assert log["failure_count"] == 0
    out = ex.deliver_extension_log(job_id="aabbccdd", log=log, offer=None)
    assert "exit=0" in out["done"]
