"""Hostile MRB coverage for bobiverse#1300 / FR #1116 idle offerable gate."""
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
import queue_flow  # noqa: E402


def _write_digest(digest: Path, machines: dict) -> None:
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    for mid, workers in machines.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {
            str(pid): {"state": state, "nick": f"{mid}-{pid}"} for pid, state in workers.items()
        }
    bobreport.save_digest(digest, doc)


def _args(chair: Path, digest: Path):
    return type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()


def test_no_idle_seats_is_ok_even_with_offerable_work(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest(digest, {"marchhare": {1: "doing"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#42",
                        "title": "FR: real work",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#42",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["idle_seats"] == []


def test_require_machine_pin_with_no_matching_idle_seat_is_ok(tmp_path, monkeypatch):
    """FR #1116 evidence class: ce-priority-dev1 pin while only marchhare idle."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest(digest, {"marchhare": {41928: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/agentic_fomprep",
                        "task": "FR",
                        "id": "#56",
                        "require_machine": "ce-priority-dev1",
                        "title": "WP0 live",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/agentic_fomprep#56",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 0, payload
    assert payload["offerable_for_live_seats"] == 0
    assert payload["unaccepted_count"] == 1


def test_skip_label_umbrella_is_not_offerable(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest(digest, {"marchhare": {1: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#7",
                        "title": "Umbrella board",
                        "labels": ["umbrella", "feature-request"],
                        "line": "FR SimonBarnett/bobiverse#7",
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 0, payload
    assert payload["offerable_for_live_seats"] == 0


def test_queue_flow_offerable_count_uses_gates(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest(digest, {"marchhare": {1: "idle"}})
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
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = queue_flow.check(_args(chair, digest))
    assert payload["offerable_count"] == 0
    # empty offerable is itself a queue_flow finding
    assert code == 1
    assert any("offer queue empty" in f for f in payload["findings"])


def test_count_offerable_helper_zero_without_nicks():
    assert idle_seats.count_offerable_for_live_seats(Path("."), [{"task": "FR"}], []) == 0
