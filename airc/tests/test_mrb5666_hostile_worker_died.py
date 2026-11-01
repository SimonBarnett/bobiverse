"""MRB #5666 hostile pins for FR #5665 isolated worker_died fail-closed."""
from __future__ import annotations

import subprocess

import airc_extension as ex
import airc_isolated as iso
import airc_legion as lg


def test_mrb5666_timeout_is_worker_died():
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    out = iso.call_isolated_module(
        "airc_extension",
        "fill_holes_work",
        {},
        runner=boom,
    )
    assert out["ok"] is False
    assert out["error"] == "worker_died"
    assert "timeout" in str(out.get("detail") or "").lower()


def test_mrb5666_happy_path_still_returns_payload():
    class P:
        returncode = 0
        stdout = '{"ok": true, "hosts": [{"host": "pc1", "ok": true}]}'
        stderr = ""

    out = iso.call_isolated_module(
        "airc_extension",
        "fill_holes_work",
        {},
        runner=lambda *_a, **_k: P(),
    )
    assert out["ok"] is True
    assert out["hosts"][0]["host"] == "pc1"
    assert out.get("error") != "worker_died"


def test_mrb5666_nondict_payload_is_worker_fault():
    assert iso.is_worker_fault(None) is True
    assert iso.is_worker_fault("x") is True
    assert iso.is_worker_fault([]) is True


def test_mrb5666_extension_empty_success_still_distinct_from_worker_died():
    """Legitimate empty/skipped GPO must not be remapped to worker_died."""
    log = ex.extension_log_from_payload(
        "install",
        whatif=True,
        payload={
            "ok": True,
            "hosts": [],
            "gpo_detail": {
                "ok": True,
                "attempted": False,
                "reason": "gpo_step_skipped",
                "wrote_gpo": False,
            },
        },
    )
    assert (log.get("gpo") or {}).get("reason") == "gpo_step_skipped"
    assert not any(f.get("error") == "worker_died" for f in (log.get("failures") or []))


def test_mrb5666_legion_build_deliver_worker_died_exit_1():
    log = lg.build_legion_log(
        target="flamingo",
        whatif=True,
        summary="failed",
        failures=[{"host": "flamingo", "error": "worker_died", "detail": "exit-1"}],
    )
    assert log["failure_count"] >= 1
    delivered = lg.deliver_legion_log(job_id="aabbccdd", log=log, offer=None)
    assert "exit=1" in delivered["done"]
    assert "exit=0" not in delivered["done"].split()
