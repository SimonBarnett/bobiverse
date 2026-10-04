"""FR #1625: no false starve while offered_to awaits ACK; drop w-mh-* ghosts; dedupe nicks."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bobreport
import registered_machines

MON = Path(__file__).resolve().parents[1] / "tools" / "monitor"
sys.path.insert(0, str(MON))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))

import idle_seats  # noqa: E402
import queue_flow  # noqa: E402


def _args(chair: Path, digest: Path):
    return type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()


def _iso_ago(seconds: float) -> str:
    ts = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return ts.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_digest_workers(digest: Path, machine: str, entries: list[dict]) -> None:
    """Write digest with both pid workers and optional worker_list ghosts (FR #1625 evidence)."""
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    doc["machines"][machine] = bobreport._empty_machine(machine)
    workers = {}
    wlist = []
    for e in entries:
        nick = str(e["nick"])
        state = str(e.get("state") or "idle")
        pid = e.get("pid")
        if pid is not None:
            workers[str(pid)] = {"state": state, "nick": nick}
        wlist.append({"nick": nick, "state": state, "pid": pid})
    doc["machines"][machine]["workers"] = workers
    doc["machines"][machine]["worker_list"] = wlist
    bobreport.save_digest(digest, doc)


def test_is_starve_idle_nick_drops_ghosts_and_ears():
    assert idle_seats.is_starve_idle_nick("marchhare-41928") is True
    assert idle_seats.is_starve_idle_nick("win-mpre8vi4u6u-20596") is True
    assert idle_seats.is_starve_idle_nick("w-mh-41912") is False
    assert idle_seats.is_starve_idle_nick("w-io-16564") is False
    assert idle_seats.is_starve_idle_nick("bob-marchhare") is False
    assert idle_seats.is_starve_idle_nick("") is False
    assert idle_seats.is_starve_idle_nick("marchhare") is False


def test_row_offer_pending_within_and_past_grace():
    fresh = {"offered_to": "marchhare-41928", "offered_ts": _iso_ago(10)}
    stale = {"offered_to": "marchhare-41928", "offered_ts": _iso_ago(120)}
    empty = {"offered_to": "", "offered_ts": _iso_ago(5)}
    assert idle_seats.row_offer_pending(fresh, timeout_s=90) is True
    assert idle_seats.row_offer_pending(stale, timeout_s=90) is False
    assert idle_seats.row_offer_pending(empty, timeout_s=90) is False


def test_collect_idle_shop_seats_filters_ghosts_and_dedupes():
    machines = {
        "marchhare": {
            "workers": {
                "41928": {"state": "idle", "nick": "marchhare-41928"},
                "41912": {"state": "idle", "nick": "w-mh-41912"},
            },
            "worker_list": [
                {"nick": "marchhare-41928", "state": "idle", "pid": None},
                {"nick": "w-mh-16564", "state": "idle"},
                {"nick": "marchhare-3556", "state": "doing"},
            ],
        }
    }
    idle = idle_seats.collect_idle_shop_seats(machines)
    nicks = sorted(x["nick"] for x in idle)
    assert nicks == ["marchhare-41928"]
    assert all(idle_seats.is_starve_idle_nick(n) for n in nicks)


def test_idle_seats_ok_when_only_row_is_offered_pending(tmp_path, monkeypatch):
    """Evidence class from FR #1625: offered_to awaiting ACK must not EXIT 1."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest_workers(
        digest,
        "marchhare",
        [
            {"nick": "marchhare-41928", "state": "idle", "pid": 41928},
            {"nick": "w-mh-41912", "state": "idle", "pid": 41912},
            {"nick": "marchhare-41928", "state": "idle", "pid": None},
        ],
    )
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
                    },
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1622",
                        "title": "FR: BoredEmitter harvest hold",
                        "labels": ["feature-request", "via-intake"],
                        "line": "FR SimonBarnett/bobiverse#1622",
                        "offered_to": "marchhare-41928",
                        "offered_ts": _iso_ago(5),
                    },
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
    assert payload["offerable_for_live_seats"] == 0
    assert int(payload.get("pending_offer_count") or 0) == 1
    idle_nicks = [x["nick"] for x in payload["idle_seats"]]
    assert "marchhare-41928" in idle_nicks
    assert not any(n.startswith("w-") for n in idle_nicks)
    assert idle_nicks.count("marchhare-41928") == 1
    notes = " ".join(payload.get("notes") or [])
    assert "offered_to" in notes and "1625" in notes


def test_queue_flow_ok_when_only_ungated_is_offered_pending(tmp_path, monkeypatch):
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest_workers(
        digest,
        "marchhare",
        [
            {"nick": "marchhare-41928", "state": "idle", "pid": 41928},
            {"nick": "w-mh-41912", "state": "idle", "pid": 41912},
        ],
    )
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    (digest / "queue.json").write_text(
        json.dumps(
            {
                "v": 1,
                "unaccepted": [
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1102",
                        "require_machine": "ce-priority-dev1",
                        "title": "DEV1 pin",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#1102",
                    },
                    {
                        "repo": "SimonBarnett/bobiverse",
                        "task": "FR",
                        "id": "#1622",
                        "title": "FR: offered pending",
                        "labels": ["feature-request", "via-intake"],
                        "line": "FR SimonBarnett/bobiverse#1622",
                        "offered_to": "marchhare-41928",
                        "offered_ts": _iso_ago(8),
                    },
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = queue_flow.check(_args(chair, digest))
    assert code == 0, payload
    assert payload["ok"] is True
    assert int(payload.get("ungated_offerable_count") or 0) == 0
    assert int(payload.get("pending_offer_count") or 0) == 1
    # Ghosts must not inflate idle_seat_count for starve math.
    assert int(payload.get("idle_seat_count") or 0) == 1
    notes = " ".join(payload.get("notes") or [])
    assert "offered_to" in notes
    assert "true starve" not in " ".join(payload.get("findings") or [])


def test_expired_offered_to_still_counts_as_offerable(tmp_path, monkeypatch):
    """Past OFFER_TIMEOUT_S the row is starve-offerable again (chair would clear stamp)."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_digest_workers(
        digest,
        "marchhare",
        [{"nick": "marchhare-41928", "state": "idle", "pid": 41928}],
    )
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
                        "title": "FR: stale offer",
                        "labels": ["feature-request"],
                        "line": "FR SimonBarnett/bobiverse#99",
                        "offered_to": "marchhare-99999",
                        "offered_ts": _iso_ago(200),
                    }
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )
    payload, code = idle_seats.check(_args(chair, digest))
    assert code == 1, payload
    assert payload["offerable_for_live_seats"] >= 1
    assert int(payload.get("pending_offer_count") or 0) == 0
