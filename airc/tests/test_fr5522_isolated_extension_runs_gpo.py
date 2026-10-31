"""FR #5522: isolated EXTENSION child must run extension_gpo_then_fill_holes (not fill_holes only)."""
from __future__ import annotations

import json
import time

import airc_extension as ex
import airc_isolated as iso


def test_fr5522_packaged_work_includes_gpo_then_fill_holes():
    assert iso.is_packaged_work(ex.extension_gpo_then_fill_holes)
    assert iso.is_packaged_work(ex.fill_holes_work)


def test_fr5522_service_runner_isolates_gpo_then_fill_holes(monkeypatch):
    seen: list[tuple] = []

    def fake(module, func, kwargs, **_k):
        seen.append((module, func, dict(kwargs)))
        return {
            "ok": True,
            "gpo": "ok",
            "gpo_detail": {"ok": True, "gpo": "ok", "wrote_gpo": True, "gpo_name": "Priority-web-extension"},
            "wrote_gpo": True,
            "hosts": [],
            "failures": [],
        }

    monkeypatch.setattr(iso, "call_isolated_module", fake)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake)
    res = ex.service_extension_runner(action="install", whatif=True, job_id="aabbccdd")
    assert "EXTENSION accepted" in res.reply
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not seen:
        time.sleep(0.02)
    assert seen, "isolated child was not scheduled"
    assert seen[0][0] == "airc_extension"
    assert seen[0][1] == "extension_gpo_then_fill_holes"
    assert seen[0][2].get("action") == "install"
    assert seen[0][2].get("whatif") is True
    assert "password" not in json.dumps(seen[0][2])


def test_fr5522_run_extension_verb_uses_worker_name(monkeypatch):
    seen: list[tuple] = []

    def fake(module, func, kwargs, **_k):
        seen.append((module, func, dict(kwargs)))
        return {"ok": True, "gpo": "ok", "gpo_detail": {"ok": True, "gpo": "ok"}, "hosts": []}

    monkeypatch.setattr(iso, "call_isolated_module", fake)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake)
    ex.run_extension_verb(
        action="install",
        whatif=False,
        job_id="11223344",
        worker=ex.extension_gpo_then_fill_holes,
        wait=False,
    )
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not seen:
        time.sleep(0.02)
    assert seen and seen[0][1] == "extension_gpo_then_fill_holes"


def test_fr5522_fill_holes_only_worker_still_packaged(monkeypatch):
    seen: list[tuple] = []

    def fake(module, func, kwargs, **_k):
        seen.append((module, func, dict(kwargs)))
        return {"ok": True, "hosts": [], "failures": []}

    monkeypatch.setattr(iso, "call_isolated_module", fake)
    monkeypatch.setattr("airc_isolated.call_isolated_module", fake)
    ex.run_extension_verb(
        action="status",
        worker=ex.fill_holes_work,
        wait=False,
        job_id="55667788",
    )
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not seen:
        time.sleep(0.02)
    assert seen and seen[0][1] == "fill_holes_work"


def test_fr5522_log_fill_holes_only_does_not_claim_gpo_ok():
    """FR #5586 twin: fill-holes-only payload must not invent gpo attempted/ok."""
    log = ex.extension_log_from_payload(
        "install",
        whatif=False,
        payload={"ok": True, "hosts": [{"hostname": "box1", "status": "ok"}], "failures": []},
    )
    gpo = log.get("gpo") or {}
    assert gpo.get("attempted") is False
    assert gpo.get("ok") is not True


def test_fr5522_log_with_gpo_detail_keeps_attempted():
    log = ex.extension_log_from_payload(
        "install",
        payload={
            "ok": True,
            "gpo": "ok",
            "gpo_detail": {
                "ok": True,
                "gpo": "ok",
                "gpo_name": "Priority-web-extension",
                "wrote_gpo": True,
                "browsers": ["chrome", "edge"],
            },
            "hosts": [],
            "failures": [],
        },
    )
    gpo = log.get("gpo") or {}
    assert gpo.get("attempted") is True
    assert gpo.get("ok") is True
    assert gpo.get("result") == "ok"
