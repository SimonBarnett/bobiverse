# -*- coding: utf-8 -*-
"""FR #9826: Jeeves on IRC => local /bob/v1/report HTTP 200 (same-turn bring-up)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves"
MON = JEEVES / "tools" / "monitor"
sys.path.insert(0, str(MON))

import webhooks_up_with_chair as wuc  # noqa: E402

START = JEEVES / "scripts" / "Start-Jeeves.ps1"
INVOKE = JEEVES / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
TEST_WRAP = JEEVES / "scripts" / "Test-JeevesMonitorWebhooksUpWithChair.ps1"
AGENTS = JEEVES / "AGENTS.md"
WEBHOOKS_DOC = JEEVES / "docs" / "webhooks.md"
MONITOR_SKILL = JEEVES / ".grok" / "skills" / "monitor-start" / "SKILL.md"


def test_fr9826_start_jeeves_asserts_local_report_http_200():
    t = START.read_text(encoding="utf-8")
    assert "FR #9826" in t
    assert "Test-BobCallbackReportOk" in t
    assert "Wait-BobCallbackReportOk" in t
    assert "http://127.0.0.1:7700/bob/v1/report" in t
    assert "W3SVC" in t
    assert "BobIrcd" in t  # never-touch reminder in heal path comments / prior script


def test_fr9826_monitor_check_wired():
    inv = INVOKE.read_text(encoding="utf-8")
    assert "webhooks_up_with_chair" in inv
    assert TEST_WRAP.is_file()
    wrap = TEST_WRAP.read_text(encoding="utf-8-sig")
    assert "webhooks_up_with_chair" in wrap
    assert (MON / "webhooks_up_with_chair.py").is_file()


def test_fr9826_docs_and_agents_cast_iron():
    agents = AGENTS.read_text(encoding="utf-8")
    assert "FR #9826" in agents
    assert "webhooks_up_with_chair" in agents
    assert "Test-JeevesMonitorWebhooksUpWithChair" in agents
    wh = WEBHOOKS_DOC.read_text(encoding="utf-8")
    assert "FR #9826" in wh
    skill = MONITOR_SKILL.read_text(encoding="utf-8")
    assert "webhooks_up_with_chair" in skill
    assert "9826" in skill


def test_fr9826_finding_when_chair_up_report_down(monkeypatch):
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "0")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Running" if name == "ircJeeves" else "missing")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: False)
    monkeypatch.setattr(wuc, "probe_local_report", lambda *a, **k: (False, 0, "URLError:refused"))
    monkeypatch.setattr(wuc, "probe_public_report", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    monkeypatch.setattr(wuc, "non_chair_overlay", lambda *a, **k: None)
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_FINDING
    assert payload["ok"] is False
    assert any("9826" in f for f in payload["findings"])


def test_fr9826_ok_when_chair_up_report_200(monkeypatch):
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "0")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Running")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(wuc, "probe_local_report", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(wuc, "probe_public_report", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_OK
    assert payload["ok"] is True
    assert payload["local_report_ok"] is True


def test_fr9826_ok_when_chair_not_running(monkeypatch):
    """Stopped + not intended-up (Disabled) stays soft-ok; FR #9836 covers Automatic."""
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "0")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Stopped")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Disabled")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: False)
    monkeypatch.setattr(wuc, "probe_local_report", lambda *a, **k: (False, 0, "refused"))
    monkeypatch.setattr(wuc, "probe_public_report", lambda *a, **k: (False, 502, "http=502"))
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_OK
    assert payload["ok"] is True
    assert payload["ircJeeves"] == "Stopped"


def test_fr9826_heal_then_ok(monkeypatch):
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "1")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Running")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: True)
    calls = {"n": 0}

    def _probe(*a, **k):
        calls["n"] += 1
        if calls["n"] <= 2:
            return False, 502, "http=502"
        return True, 200, "status=200"

    monkeypatch.setattr(wuc, "probe_local_report", _probe)
    monkeypatch.setattr(wuc, "probe_public_report", _probe)
    monkeypatch.setattr(
        wuc,
        "heal_bobcallback_local",
        lambda: {"ok": True, "actions": ["schtasks_start"]},
    )

    import time as time_mod

    monkeypatch.setattr(time_mod, "sleep", lambda s: None)
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    monkeypatch.setattr(wuc, "non_chair_overlay", lambda *a, **k: None)
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_OK
    assert payload["ok"] is True
    assert payload["heal"].get("bobcallback", {}).get("actions") == ["schtasks_start"]
    assert calls["n"] >= 2
