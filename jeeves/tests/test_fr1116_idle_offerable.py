"""FR #1116: idle_seats findings only when offerable work exists for live seats."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bobreport
import registered_machines

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))

import idle_seats  # noqa: E402


def _write_digest(digest: Path, machines: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {
            str(pid): {"state": state, "nick": f"{mid}-{pid}"} for pid, state in workers.items()
        }
    bobreport.save_digest(digest, doc)


def test_idle_with_only_gated_rows_is_ok(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"win-mpre8vi4u6u", "marchhare"})
    _write_digest(digest, {"win-mpre8vi4u6u": {20596: "idle"}, "marchhare": {1: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1",
                        "needs_human": True,
                        "title": "FR: human",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#1",
                    },
                    {
                        "repo": "SimonBarnett/agentic_fomprep",
                        "task": "FR",
                        "id": "#56",
                        "require_machine": "ce-priority-dev1",
                        "title": "WP0 live",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/agentic_fomprep#56",
                    },
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = idle_seats.check(args)
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["offerable_for_live_seats"] == 0
    assert payload["unaccepted_count"] == 2
    assert len(payload["idle_seats"]) == 2


def test_idle_with_offerable_row_is_finding(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"win-mpre8vi4u6u", "marchhare"})
    _write_digest(digest, {"win-mpre8vi4u6u": {20596: "idle"}, "marchhare": {1: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#99",
                        "title": "FR: real work",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#99",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    args = type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()
    payload, code = idle_seats.check(args)
    assert code == 1, payload
    assert payload["ok"] is False
    assert payload["offerable_for_live_seats"] >= 1
    assert "offerable" in (payload["findings"][0] if payload["findings"] else "")