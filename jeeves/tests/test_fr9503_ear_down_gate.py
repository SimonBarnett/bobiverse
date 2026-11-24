"""FR #9503: ear-down FRs need bob-ear + digest online gate before Closes."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "tools" / "monitor"
IRCBOB = MONITOR / "ircbob_ear.py"
GATE = MONITOR / "ear_down_gate.py"


def _import_gate():
    sys.path.insert(0, str(MONITOR))
    import ear_down_gate as mod  # noqa: WPS433

    return mod


def _import_ircbob():
    sys.path.insert(0, str(MONITOR))
    import ircbob_ear as mod  # noqa: WPS433

    return mod


def test_fr9503_is_ear_down_issue_classifier():
    g = _import_gate()
    assert g.is_ear_down_issue(
        "marchhare bob-ear dead after ENOSPC; ircBob nssm Running without bob-ear child"
    )
    assert g.is_ear_down_issue(
        "FR: do not close marchhare ear-down without gate",
        "bob-ear.exe count stayed 0",
    )
    assert not g.is_ear_down_issue("Weights UI polish", "tray menu only")


def test_fr9503_closes_allowed_only_when_gate_ok():
    g = _import_gate()
    title = "marchhare bob-ear dead; ircBob Running without child"
    assert g.closes_allowed_for_ear_down(title, gate_ok=False) is False
    assert g.closes_allowed_for_ear_down(title, gate_ok=True) is True
    assert g.closes_allowed_for_ear_down("unrelated FR", gate_ok=False) is True


def test_fr9503_gate_requires_child_and_digest_online():
    g = _import_gate()
    now = time.time()
    fresh = (
        datetime.now(timezone.utc) - timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    ent = {"online": True, "status": "I am online", "lastSeen": fresh}
    bad = g.ear_down_gate(
        ear_child_alive=False, machine_ent=ent, now=now, startworker_acked=None
    )
    assert bad["ok"] is False
    assert any("child" in r.lower() for r in bad["reasons"])

    offline = g.ear_down_gate(
        ear_child_alive=True,
        machine_ent={"online": False, "lastSeen": fresh},
        now=now,
    )
    assert offline["ok"] is False

    good = g.ear_down_gate(
        ear_child_alive=True, machine_ent=ent, now=now, startworker_acked=None
    )
    assert good["ok"] is True

    sw = g.ear_down_gate(
        ear_child_alive=True,
        machine_ent=ent,
        now=now,
        startworker_acked=False,
    )
    assert sw["ok"] is False
    assert any("startworker" in r.lower() for r in sw["reasons"])


def test_fr9503_gate_module_utf8_no_bom():
    assert not GATE.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "9503" in GATE.read_text(encoding="utf-8")


def test_fr9503_job_fr_skill_refs_until_gate():
    skill = ROOT.parents[0] / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "9503" in text
    assert "Refs" in text
    assert "ear_down_gate" in text or "ear-down" in text.lower()


class _Args:
    def __init__(self, tmp_path: Path):
        self.chair_home = str(tmp_path / "jeeves-home")
        self.digest_home = str(tmp_path)


def test_fr9503_ircbob_heal_still_finding_when_digest_offline(
    tmp_path: Path, monkeypatch
):
    """Heal Restart success is not EXIT_OK while digest still shows offline."""
    now = datetime.now(timezone.utc)
    digest = {
        "ts": now.isoformat().replace("+00:00", "Z"),
        "machines": {
            "marchhare": {
                "online": False,
                "status": "I am offline",
                "lastSeen": (now - timedelta(seconds=10))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        },
    }
    (tmp_path / "digest.json").write_text(json.dumps(digest), encoding="utf-8")
    (tmp_path / "jeeves-home").mkdir(parents=True, exist_ok=True)

    mod = _import_ircbob()
    monkeypatch.setenv("DIGEST_ID", "marchhare")
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Running")
    child = iter([False, True])
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: next(child))
    monkeypatch.setattr(mod, "_restart_service", lambda _n: (True, "ok"))
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload.get("heal") == "restarted"
    assert payload.get("ear_child_alive") is True
    gate = payload.get("ear_down_gate") or {}
    assert gate.get("ok") is False
    assert any("9503" in f for f in payload["findings"])


def test_fr9503_ircbob_ok_when_child_and_digest_online(tmp_path: Path, monkeypatch):
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

    mod = _import_ircbob()
    monkeypatch.setenv("DIGEST_ID", "marchhare")
    monkeypatch.setattr(mod, "_service_state", lambda _n: "Running")
    monkeypatch.setattr(mod, "_ear_child_alive", lambda: True)
    monkeypatch.setattr(mod, "_scan_enospc_logs", lambda: [])

    payload, code = mod.check(_Args(tmp_path))
    assert code == 0, payload
    assert payload["ok"] is True
    assert (payload.get("ear_down_gate") or {}).get("ok") is True
