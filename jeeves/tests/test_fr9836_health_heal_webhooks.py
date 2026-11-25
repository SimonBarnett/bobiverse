# -*- coding: utf-8 -*-
"""FR #9836: health EXIT 1 + heal starts chair; probe local and public report."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
JEEVES = ROOT / "jeeves"
MON = JEEVES / "tools" / "monitor"
COMMON = ROOT / "common" / "scripts"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(COMMON))

import health  # noqa: E402
import webhooks_up_with_chair as wuc  # noqa: E402

START = JEEVES / "scripts" / "Start-Jeeves.ps1"
INVOKE = JEEVES / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
AGENTS = JEEVES / "AGENTS.md"
WEBHOOKS_DOC = JEEVES / "docs" / "webhooks.md"
JEEVES_MAIN = COMMON / "jeeves_main.py"


def _args(tmp_path: Path, dry_run: bool = False):
    return SimpleNamespace(
        chair_home=str(tmp_path),
        digest_home=str(tmp_path),
        dry_run=dry_run,
    )


def test_fr9836_docs_and_wiring():
    health_src = (MON / "health.py").read_text(encoding="utf-8")
    assert "9836" in health_src
    assert "probe_public_report" in health_src or "public_report" in health_src
    assert "heal_start_ircjeeves" in health_src
    main_src = JEEVES_MAIN.read_text(encoding="utf-8")
    assert "9836" in main_src
    assert "heal_start_ircjeeves" in main_src or "Start-Service ircJeeves" in main_src or "ircJeeves" in main_src
    wh = WEBHOOKS_DOC.read_text(encoding="utf-8")
    assert "9836" in wh
    agents = AGENTS.read_text(encoding="utf-8")
    assert "9836" in agents
    inv = INVOKE.read_text(encoding="utf-8")
    assert "health" in inv
    assert "webhooks_up_with_chair" in inv


def test_fr9836_stopped_intended_up_is_finding(tmp_path, monkeypatch):
    """Stop chair (Automatic) while Ergo up => health EXIT 1."""
    monkeypatch.setenv("BOB_HEALTH_AUTO", "0")
    tmp_path.mkdir(parents=True, exist_ok=True)

    def fake_state(name: str) -> str:
        return {
            "ircJeeves": "Stopped",
            "BobIrcd": "Running",
            "BobCallback": "missing",
        }.get(name, "missing")

    def fake_start(name: str) -> str:
        return {"ircJeeves": "Automatic", "BobIrcd": "Automatic"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: False)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")
    monkeypatch.setattr(health, "non_chair_overlay", lambda *a, **k: None)
    monkeypatch.setattr(
        health,
        "probe_local_report",
        lambda *a, **k: (False, 0, "refused"),
    )
    monkeypatch.setattr(
        health,
        "probe_public_report",
        lambda *a, **k: (False, 502, "http=502"),
    )

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_FINDING
    assert payload["ok"] is False
    assert any("ircJeeves" in f for f in payload["findings"])


def test_fr9836_running_public_502_is_finding(tmp_path, monkeypatch):
    """Fail-when: chair Running + public 502 must not stay EXIT 0."""
    monkeypatch.setenv("BOB_HEALTH_AUTO", "0")
    tmp_path.mkdir(parents=True, exist_ok=True)

    def fake_state(name: str) -> str:
        return {
            "ircJeeves": "Running",
            "BobIrcd": "Running",
            "BobCallback": "missing",
        }.get(name, "missing")

    def fake_start(name: str) -> str:
        return {"ircJeeves": "Automatic", "BobIrcd": "Automatic"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")
    monkeypatch.setattr(health, "non_chair_overlay", lambda *a, **k: None)
    monkeypatch.setattr(
        health,
        "probe_local_report",
        lambda *a, **k: (True, 200, "status=200"),
    )
    monkeypatch.setattr(
        health,
        "probe_public_report",
        lambda *a, **k: (False, 502, "http=502"),
    )

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_FINDING
    assert payload["ok"] is False
    assert payload.get("public_report_ok") is False
    assert any("9836" in f or "502" in f or "public" in f.lower() for f in payload["findings"])


def test_fr9836_heal_starts_chair_then_ok(tmp_path, monkeypatch):
    """Heal starts ircJeeves and re-probes local+public before OK."""
    monkeypatch.setenv("BOB_HEALTH_AUTO", "1")
    tmp_path.mkdir(parents=True, exist_ok=True)
    state = {"ircJeeves": "Stopped"}

    def fake_state(name: str) -> str:
        if name == "ircJeeves":
            return state["ircJeeves"]
        return {
            "BobIrcd": "Running",
            "BobCallback": "missing",
        }.get(name, "missing")

    def fake_start(name: str) -> str:
        return {"ircJeeves": "Automatic", "BobIrcd": "Automatic"}.get(name, "missing")

    probes = {"n": 0}

    def _local(*a, **k):
        probes["n"] += 1
        if state["ircJeeves"].lower() != "running":
            return False, 0, "refused"
        return True, 200, "status=200"

    def _public(*a, **k):
        if state["ircJeeves"].lower() != "running":
            return False, 502, "http=502"
        return True, 200, "status=200"

    def _heal_start():
        state["ircJeeves"] = "Running"
        return {"ok": True, "actions": ["service_start"]}

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: state["ircJeeves"] == "Running")
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")
    monkeypatch.setattr(health, "non_chair_overlay", lambda *a, **k: None)
    monkeypatch.setattr(health, "probe_local_report", _local)
    monkeypatch.setattr(health, "probe_public_report", _public)
    monkeypatch.setattr(health, "heal_start_ircjeeves", _heal_start)
    monkeypatch.setattr(
        health,
        "heal_bobcallback_local",
        lambda: {"ok": True, "actions": ["schtasks_start"]},
    )

    import time as time_mod

    monkeypatch.setattr(time_mod, "sleep", lambda s: None)

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_OK
    assert payload["ok"] is True
    assert state["ircJeeves"] == "Running"
    assert payload.get("heal", {}).get("ircjeeves", {}).get("actions") == ["service_start"]
    assert payload.get("local_report_ok") is True
    assert payload.get("public_report_ok") is True


def test_fr9836_webhooks_check_starts_stopped_chair(monkeypatch):
    """webhooks_up_with_chair: Stopped+Automatic+Ergo-up heals by starting chair."""
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "1")
    state = {"ircJeeves": "Stopped"}

    def fake_state(name: str) -> str:
        if name == "ircJeeves":
            return state["ircJeeves"]
        if name == "BobIrcd":
            return "Running"
        return "missing"

    def fake_start(name: str) -> str:
        return "Automatic"

    calls = {"n": 0}

    def _probe(*a, **k):
        calls["n"] += 1
        if state["ircJeeves"].lower() != "running":
            return False, 502, "http=502"
        return True, 200, "status=200"

    monkeypatch.setattr(wuc, "_service_state", fake_state)
    monkeypatch.setattr(wuc, "_service_start_type", fake_start)
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: state["ircJeeves"] == "Running")
    monkeypatch.setattr(wuc, "probe_local_report", _probe)
    monkeypatch.setattr(wuc, "probe_public_report", _probe)
    monkeypatch.setattr(
        wuc,
        "heal_start_ircjeeves",
        lambda: (state.__setitem__("ircJeeves", "Running") or {"ok": True, "actions": ["service_start"]}),
    )
    monkeypatch.setattr(
        wuc,
        "heal_bobcallback_local",
        lambda: {"ok": True, "actions": ["schtasks_start"]},
    )
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    monkeypatch.setattr(wuc, "non_chair_overlay", lambda *a, **k: None)

    import time as time_mod

    monkeypatch.setattr(time_mod, "sleep", lambda s: None)

    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_OK
    assert payload["ok"] is True
    assert state["ircJeeves"] == "Running"


def test_fr9836_webhooks_running_public_502_finding(monkeypatch):
    monkeypatch.setenv("BOB_WEBHOOKS_UP_AUTO", "0")
    monkeypatch.setattr(wuc, "_service_state", lambda name: "Running")
    monkeypatch.setattr(wuc, "_service_start_type", lambda name: "Automatic")
    monkeypatch.setattr(wuc, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(wuc, "probe_local_report", lambda *a, **k: (True, 200, "status=200"))
    monkeypatch.setattr(wuc, "probe_public_report", lambda *a, **k: (False, 502, "http=502"))
    monkeypatch.setattr(
        wuc,
        "resolve_homes",
        lambda args: (Path("C:/tmp/chair"), Path("C:/tmp/digest")),
    )
    monkeypatch.setattr(wuc, "non_chair_overlay", lambda *a, **k: None)
    payload, code = wuc.check(SimpleNamespace(dry_run=False))
    assert code == wuc.EXIT_FINDING
    assert payload["ok"] is False
    assert payload.get("public_report_ok") is False
