"""FR #6587: BobIrcd Stopped+Disabled is a soft note, not a heal/self-test finding."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))

import health  # noqa: E402


def _args(tmp_path: Path):
    return type("A", (), {"chair_home": str(tmp_path), "digest_home": str(tmp_path)})()


def test_fr6587_bobircd_stopped_disabled_ok(tmp_path, monkeypatch):
    """Remote-Ergo hosts leave BobIrcd Disabled: health must exit 0."""
    tmp_path.mkdir(parents=True, exist_ok=True)

    def fake_state(name: str) -> str:
        return {"ircJeeves": "Running", "BobIrcd": "Stopped", "BobCallback": "missing"}.get(
            name, "missing"
        )

    def fake_start(name: str) -> str:
        return {"BobIrcd": "Disabled", "ircJeeves": "Automatic"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_OK
    assert payload["ok"] is True
    assert not any("BobIrcd" in f for f in payload["findings"])
    assert payload["services"]["BobIrcd"].lower().startswith("stopped")
    notes = payload.get("notes") or []
    assert any("BobIrcd" in n and "Disabled" in n for n in notes)


def test_fr6587_bobircd_stopped_automatic_is_finding(tmp_path, monkeypatch):
    """Local Ergo expected: Stopped + Automatic remains a finding."""

    def fake_state(name: str) -> str:
        return {"ircJeeves": "Running", "BobIrcd": "Stopped", "BobCallback": "missing"}.get(
            name, "missing"
        )

    def fake_start(name: str) -> str:
        return {"BobIrcd": "Automatic", "ircJeeves": "Automatic"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_FINDING
    assert any("BobIrcd" in f and "Stopped" in f for f in payload["findings"])


def test_fr6587_ircjeeves_stopped_still_finding(tmp_path, monkeypatch):
    """ircJeeves must never soft-skip; chair down is always a finding."""

    def fake_state(name: str) -> str:
        return {"ircJeeves": "Stopped", "BobIrcd": "Stopped", "BobCallback": "missing"}.get(
            name, "missing"
        )

    def fake_start(name: str) -> str:
        return {"BobIrcd": "Disabled", "ircJeeves": "Disabled"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_FINDING
    assert any("ircJeeves" in f for f in payload["findings"])


def test_fr6587_source_pins_disabled_soft_note():
    text = (MON / "health.py").read_text(encoding="utf-8")
    assert "_service_start_type" in text
    assert "Disabled" in text
    assert "6587" in text
