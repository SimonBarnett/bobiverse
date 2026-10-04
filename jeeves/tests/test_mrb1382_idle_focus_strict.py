"""Hostile MRB #1382: idle_seats offerable count must respect focus.strict."""
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


def _args(chair: Path, digest: Path):
    return type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()


def test_focus_strict_excludes_unfocused_plan_smoke_from_offerable(tmp_path, monkeypatch):
    """Evidence class for #1382/#1383: plan-smoke under bobiverse-only focus.strict → EXIT 0."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest(digest, {"marchhare": {41928: "idle"}})
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    # Chair focus lives next to queue (ops_home); put focus + queue on digest home.
    (digest / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {"SimonBarnett/bobiverse": {"priority": 1}},
            }
        ),
        encoding="utf-8",
    )
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/plan-smoke",
                        "task": "FR",
                        "id": "#1",
                        "title": "FR: plan smoke",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/plan-smoke#1",
                        "state": "open",
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


def test_count_helper_drops_unfocused_under_strict(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    (home / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {"SimonBarnett/bobiverse": {"priority": 1}},
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "repo": "SimonBarnett/plan-smoke",
            "task": "FR",
            "id": "#1",
            "title": "FR: plan smoke",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/plan-smoke#1",
            "state": "open",
        }
    ]
    n = idle_seats.count_offerable_for_live_seats(home, rows, ["marchhare-41928"])
    assert n == 0


def test_focused_bobiverse_row_still_counts_under_strict(tmp_path, monkeypatch):
    home = tmp_path
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    registered_machines.save_registered(home, {"marchhare"})
    (home / "focus.json").write_text(
        json.dumps(
            {
                "v": 1,
                "strict": True,
                "repos": {"SimonBarnett/bobiverse": {"priority": 1}},
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "FR",
            "id": "#42",
            "title": "FR: real work",
            "labels": ["feature-request"],
            "line": "FR SimonBarnett/bobiverse#42",
            "state": "open",
        }
    ]
    n = idle_seats.count_offerable_for_live_seats(home, rows, ["marchhare-41928"])
    assert n == 1
