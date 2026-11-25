# -*- coding: utf-8 -*-
"""FR #9864: report must soft-degrade within budget; digest stays up; XOR heal fingerprint."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves"
MON = JEEVES / "tools" / "monitor"
COMMON = ROOT / "common" / "scripts"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(MON))

import bobcallback  # noqa: E402
import bobreport  # noqa: E402
import health  # noqa: E402
import webhooks_up_with_chair as wuc  # noqa: E402

INSTALL = JEEVES / "scripts" / "Install-BobWebhooks.ps1"
WEBHOOKS_DOC = JEEVES / "docs" / "webhooks.md"
AGENTS = JEEVES / "AGENTS.md"
WH_DOCS = COMMON / "bob_webhook_docs.py"


@pytest.fixture(autouse=True)
def _clear_last_good():
    bobreport.clear_last_good_report()
    yield
    bobreport.clear_last_good_report()


def test_fr9864_docs_and_iis_rewrite_digest_to_backend():
    """Digest must hit bobcallback (rewrite), not client-redirect to report."""
    txt = INSTALL.read_text(encoding="utf-8-sig")
    assert "9864" in txt
    assert 'Match = \'^bob/v1/digest$\'' in txt or "bob/v1/digest$" in txt
    # Prefer Rewrite to backend digest so digest-ok XOR report-fail is observable.
    assert ("$Backend/bob/v1/digest" in txt or "$BackendUrl/bob/v1/digest" in txt)
    assert "Rewrite" in txt
    wh = WEBHOOKS_DOC.read_text(encoding="utf-8")
    assert "9864" in wh
    assert "degraded" in wh.lower() or "soft-degrade" in wh.lower()
    agents = AGENTS.read_text(encoding="utf-8")
    assert "9864" in agents
    docs_py = WH_DOCS.read_text(encoding="utf-8")
    assert "9864" in docs_py


def test_fr9864_slow_fleet_pools_report_degrades_within_budget(tmp_path, monkeypatch):
    """Forced slow fleet-pools => report returns 200 degraded within N seconds."""
    bobreport.save_digest(tmp_path, bobreport.empty_digest())
    monkeypatch.setenv("BOB_REPORT_BUILD_BUDGET_S", "0.4")

    def slow_fleet(home, doc):
        time.sleep(2.0)
        return {"copilot": {"state": "ok", "remaining": 1}}

    monkeypatch.setattr(bobreport, "_report_fleet_pools_fetch", slow_fleet)
    t0 = time.monotonic()
    code, body = bobcallback.handle_digest_get(tmp_path, "Jeeves")
    took = time.monotonic() - t0
    assert code == 200
    assert took < 1.2, f"report hung {took:.2f}s (expected soft-degrade within budget)"
    doc = json.loads(body.decode("utf-8"))
    assert doc.get("degraded") is True
    parts = doc.get("degraded_parts") or []
    assert "fleet_pools" in parts


def test_fr9864_digest_unaffected_when_report_enrichment_slow(tmp_path, monkeypatch):
    """Digest fast path stays 200 even when report fleet enrichment would hang."""
    seed = bobreport.empty_digest()
    seed["fleet_pools"] = {"copilot": {"state": "ok", "remaining": 9}}
    bobreport.save_digest(tmp_path, seed)
    # Seed last-good from a quick successful report build.
    monkeypatch.setenv("BOB_REPORT_BUILD_BUDGET_S", "5")
    code0, body0 = bobcallback.handle_digest_get(tmp_path, "Jeeves")
    assert code0 == 200 and body0
    bobreport.remember_last_good_report(json.loads(body0.decode("utf-8")), body0)

    def hang_fleet(home, doc):
        time.sleep(5.0)
        return {}

    monkeypatch.setattr(bobreport, "_report_fleet_pools_fetch", hang_fleet)
    monkeypatch.setenv("BOB_REPORT_BUILD_BUDGET_S", "0.3")

    t0 = time.monotonic()
    code, body = bobcallback.handle_digest_alias_get(tmp_path, "Jeeves")
    took = time.monotonic() - t0
    assert code == 200
    assert took < 0.8, f"digest path blocked {took:.2f}s"
    doc = json.loads(body.decode("utf-8"))
    assert isinstance(doc.get("machines"), dict)


def test_fr9864_webhooks_up_digest_ok_report_fail_is_finding(monkeypatch):
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "0")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Running")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(wuc, "probe_local_report", lambda *a, **k: (False, 0, "timeout"))
    monkeypatch.setattr(wuc, "probe_public_report", lambda *a, **k: (False, 0, "timeout"))
    monkeypatch.setattr(wuc, "probe_local_digest", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(wuc, "probe_public_digest", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    monkeypatch.setattr(wuc, "non_chair_overlay", lambda *a, **k: None)
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_FINDING
    assert payload["ok"] is False
    assert payload.get("fingerprint") == wuc.DIGEST_OK_REPORT_HANG_FP
    assert any("9864" in f for f in payload["findings"])


def test_fr9864_health_digest_ok_report_fail_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_HEALTH_AUTO", "0")
    tmp_path.mkdir(parents=True, exist_ok=True)

    def fake_state(name: str) -> str:
        return {
            "ircJeeves": "Running",
            "BobIrcd": "Running",
            "BobCallback": "Running",
        }.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", lambda *_: "Automatic")
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "Ready")
    monkeypatch.setattr(health, "non_chair_overlay", lambda *a, **k: None)
    monkeypatch.setattr(health, "probe_local_report", lambda *a, **k: (False, 0, "timeout"))
    monkeypatch.setattr(health, "probe_public_report", lambda *a, **k: (False, 0, "timeout"))
    monkeypatch.setattr(health, "probe_local_digest", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(health, "probe_public_digest", lambda *a, **k: (True, 200, "status=200"))

    payload, code = health.check(SimpleNamespace(chair_home=str(tmp_path), digest_home=str(tmp_path), dry_run=False))
    assert code == health.EXIT_FINDING
    assert payload["ok"] is False
    assert payload.get("fingerprint") == health.DIGEST_OK_REPORT_HANG_FP
    assert any("9864" in f for f in payload["findings"])
