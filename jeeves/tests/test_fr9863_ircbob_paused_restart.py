# -*- coding: utf-8 -*-
"""FR #9863: ircBob Paused (NSSM AppThrottle) must heal via Restart-Service, not Start-Service."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "tools" / "monitor" / "ircbob_ear.py"
COMMON = ROOT.parents[0] / "common" / "scripts" / "Bobiverse-Common.ps1"
PACK_SVC = ROOT.parents[0] / "bob" / "tray" / "tools" / "Invoke-BobTrayServiceControl.ps1"
HOVER = ROOT.parents[0] / "bob" / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
EAR_DOC = ROOT.parents[0] / "bob" / "docs" / "bob-ear.md"
INSTALL_BOB = ROOT.parents[0] / "bob" / "scripts" / "Install-Bob.ps1"


def _import_ircbob_ear():
    sys.path.insert(0, str(MONITOR.parent))
    import ircbob_ear as mod  # noqa: WPS433

    return mod


def _fresh_digest(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "redqueen": {
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


def test_fr9863_paused_heals_via_restart_not_start(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    states = iter(["Paused", "Running"])
    starts: list[str] = []
    restarts: list[str] = []

    monkeypatch.setattr(mod, "_service_state", lambda _n: next(states))
    # After Restart-Service heal, child must be present (FR #9863 acceptance).
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: True)
    monkeypatch.setattr(
        mod,
        "_start_service",
        lambda n: (starts.append(n) or False, "Paused"),
    )
    monkeypatch.setattr(
        mod,
        "_restart_service",
        lambda n: (restarts.append(n) or True, "Running"),
    )
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert starts == [], "Paused must not use Start-Service"
    assert restarts == [mod.SERVICE_NAME]
    assert payload["heal"] == "restarted"
    assert not any("FR #9863" in f for f in payload["findings"])
    assert code == 0, payload


def test_fr9863_paused_without_heal_is_finding(tmp_path: Path, monkeypatch):
    _fresh_digest(tmp_path)
    mod = _import_ircbob_ear()
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Paused")
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: False)
    monkeypatch.setattr(mod, "_restart_service", lambda _n: (False, "dry"))
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 1, payload
    assert any("FR #9863" in f for f in payload["findings"])
    assert any("Paused" in f for f in payload["findings"])


def test_fr9863_pins_docs_and_nssm_throttle():
    common = COMMON.read_text(encoding="utf-8")
    assert "FR #9863" in common
    assert "AppThrottle" in common
    assert "Set-BobiverseNssmAppExitRestart" in INSTALL_BOB.read_text(encoding="utf-8")
    svc = PACK_SVC.read_text(encoding="utf-8")
    assert "FR #9863" in svc
    assert "PAUSED" in svc
    hover = HOVER.read_text(encoding="utf-8")
    assert "FR #9863" in hover
    assert "Paused" in hover
    doc = EAR_DOC.read_text(encoding="utf-8")
    assert "Never Stop-Process the NSSM ear (FR #9863)" in doc
    assert "Restart-Service ircBob" in doc
    assert "9743" in doc
