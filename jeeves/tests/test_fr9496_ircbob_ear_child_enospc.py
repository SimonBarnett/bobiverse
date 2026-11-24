# -*- coding: utf-8 -*-
"""FR #9496: ircbob_ear detects Running-without-bob-ear child + ENOSPC in stderr.

Product gap vs FR #9144: Get-Service ircBob=Running while bob-ear.exe / irc_agent
is absent must EXIT 1 and attempt Restart-Service heal. ENOSPC / errno 28 in
install stderr.log must be a loud finding (chair/monitor), not silent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "tools" / "monitor" / "ircbob_ear.py"
INVOKE = ROOT / "scripts" / "Invoke-JeevesMonitorCheck.ps1"
FLEET_TRAY = (
    ROOT.parents[0] / "bob" / "tray" / "tools" / "Start-BobFleetTray.ps1"
)
HOVER = ROOT.parents[0] / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"


def _import_ircbob_ear():
    sys.path.insert(0, str(MONITOR.parent))
    import ircbob_ear as mod  # noqa: WPS433

    return mod


def _fresh_digest(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "marchhare": {
                "online": True,
                "status": "I am online",
                "lastSeen": (now - timedelta(seconds=10))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        },
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    (tmp_path / "jeeves-home").mkdir(parents=True, exist_ok=True)


class _Args:
    def __init__(self, tmp_path: Path):
        self.chair_home = str(tmp_path / "jeeves-home")
        self.digest_home = str(tmp_path)


def test_fr9496_running_without_ear_child_is_finding(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: False)
    monkeypatch.setattr(mod, "_restart_service", lambda _n: (False, "dry"))
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload.get("ear_child_alive") is False
    assert any("Running without bob-ear" in f for f in payload["findings"])


def test_fr9496_running_without_child_heals_via_restart(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    states = iter(["Running", "Running"])
    child = iter([False, True])
    restarts: list[str] = []

    monkeypatch.setattr(mod, "_service_state", lambda _n: next(states))
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: next(child))
    monkeypatch.setattr(
        mod,
        "_restart_service",
        lambda n: (restarts.append(n) or True, "Running"),
    )
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert restarts == [mod.SERVICE_NAME]
    assert payload["heal"] == "restarted"
    # After heal child alive → no Running-without finding
    assert not any("Running without bob-ear" in f for f in payload["findings"])
    assert code == 0, payload


def test_fr9496_enospc_in_stderr_is_finding(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: True)
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: ["stderr.log: ENOSPC errno 28"])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 1, payload
    assert any("ENOSPC" in f for f in payload["findings"])
    assert payload.get("enospc") is True


def test_fr9496_scan_enospc_reads_log_tail(tmp_path: Path, monkeypatch):
    mod = _import_ircbob_ear()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "stderr.log").write_text(
        "ok line\nOSError: [Errno 28] No space left on device\nmore\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "_install_root", lambda: tmp_path)
    hits = mod._scan_enospc_logs()
    assert hits, hits
    assert any("No space left" in h or "ENOSPC" in h or "Errno 28" in h for h in hits)


def test_fr9496_running_with_child_no_enospc_ok(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: True)
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload.get("ear_child_alive") is True
    assert payload.get("enospc") is False


def test_fr9496_fleet_tray_does_not_treat_running_as_ear_up():
    """Start-BobFleetTray must not set agentStillUp from ircBob Running alone."""
    text = FLEET_TRAY.read_text(encoding="utf-8")
    assert "Also treat ircBob Running as" not in text
    # Process match for bob-ear / irc_agent remains.
    assert "bob-ear" in text
    assert "irc_agent" in text


def test_fr9496_hover_reports_running_no_child():
    text = HOVER.read_text(encoding="utf-8")
    assert "Running-no-child" in text or "9496" in text
    assert "Get-BobTrayIrcBobServiceStatus" in text


def test_fr9496_monitoring_docs_mention_child_and_enospc():
    docs = ROOT / "docs" / "monitoring.md"
    text = docs.read_text(encoding="utf-8")
    assert "9496" in text
    assert "bob-ear" in text.lower() or "ear child" in text.lower()
    assert "ENOSPC" in text


def test_fr9496_test_wrapper_and_agents_row():
    wrapper = ROOT / "scripts" / "Test-JeevesMonitorIrcbobEar.ps1"
    assert wrapper.is_file()
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "ircbob_ear" in agents
    assert "9496" in agents
    assert "Test-JeevesMonitorIrcbobEar" in agents
