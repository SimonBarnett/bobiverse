"""docs/mrb-6627 hostile pins for FR #6587 BobIrcd Disabled soft-ok (PR #6627)."""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves" / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import health  # noqa: E402
import jeeves_main  # noqa: E402


def _args(tmp_path: Path):
    return type("A", (), {"chair_home": str(tmp_path), "digest_home": str(tmp_path)})()


def test_mrb6627_bobircd_stopped_manual_is_finding(tmp_path, monkeypatch):
    """Manual StartType + Stopped must remain a finding (local Ergo expected)."""

    def fake_state(name: str) -> str:
        return {"ircJeeves": "Running", "BobIrcd": "Stopped", "BobCallback": "missing"}.get(
            name, "missing"
        )

    def fake_start(name: str) -> str:
        return {"BobIrcd": "Manual", "ircJeeves": "Automatic"}.get(name, "missing")

    monkeypatch.setattr(health, "_service_state", fake_state)
    monkeypatch.setattr(health, "_service_start_type", fake_start)
    monkeypatch.setattr(health, "_port_listening", lambda *a, **k: True)
    monkeypatch.setattr(health, "_scheduled_task_state", lambda *_: "missing")

    payload, code = health.check(_args(tmp_path))
    assert code == health.EXIT_FINDING
    assert any("BobIrcd" in f and "Stopped" in f for f in payload["findings"])


def test_mrb6627_run_heal_surfaces_health_soft_notes(tmp_path, monkeypatch):
    """When health exits 0 with notes, run_heal must append those soft notes."""
    soft = "BobIrcd=Stopped/Disabled soft-ok (StartType=Disabled or skipped; FR #6587)"

    def fake_monitor(name, **kwargs):
        assert name == "health"
        return (
            {
                "ok": True,
                "services": {"ircJeeves": "Running", "BobIrcd": "Stopped/Disabled"},
                "findings": [],
                "notes": [soft],
            },
            0,
        )

    monkeypatch.setattr(jeeves_main, "run_monitor_check", fake_monitor)
    monkeypatch.setattr(jeeves_main, "_check_http", lambda: ({}, [], []))
    # Avoid maintenance spawn / lock side effects on heal exit path.
    monkeypatch.setattr(
        "jeeves_maintenance.try_start_maintenance_agent",
        lambda **_k: {"skipped": "test"},
        raising=False,
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = jeeves_main.run_heal(
            home=tmp_path,
            dry_run=True,
            force_orphan_busy=False,
            as_json=True,
            chair_home=tmp_path,
            no_maintenance_agent=True,
        )
    out = buf.getvalue()
    assert code == 0
    assert "soft-ok" in out or soft.split()[0] in out
    payload = json.loads(out.strip().splitlines()[-1])
    notes = " ".join(str(n) for n in (payload.get("notes") or []))
    assert "health: ok" in notes
    assert "BobIrcd" in notes and "soft-ok" in notes


def test_mrb6627_docs_and_source_contiguous_fr6587():
    docs = (ROOT / "jeeves" / "docs" / "jeeves-exe-self-heal.md").read_text(encoding="utf-8")
    assert "FR #6587" in docs
    assert "Disabled" in docs
    src = (MON / "health.py").read_text(encoding="utf-8")
    assert "_bobircd_expected_running" in src
    assert "6587" in src
    main = (ROOT / "common" / "scripts" / "jeeves_main.py").read_text(encoding="utf-8")
    assert 'payload.get("notes")' in main
    assert "6587" in main
