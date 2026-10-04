"""FR #1652: queue_flow starve must use idle shop nicks only (not busy + w-mh orphans)."""
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


def _args(chair: Path, digest: Path):
    return type("A", (), {"chair_home": str(chair), "digest_home": str(digest), "dry_run": False})()


def _write_busy_fleet_with_orphan_idles(digest: Path) -> None:
    """Evidence class: live seats doing; only idle rows are w-mh-* ghosts."""
    digest.mkdir(parents=True, exist_ok=True)
    doc = bobreport.empty_digest()
    for mid, seats in (
        (
            "marchhare",
            [
                ("35600", "doing", "marchhare-35600"),
                ("41928", "doing", "marchhare-41928"),
                ("41912", "idle", "w-mh-41912"),
                ("16564", "idle", "w-mh-16564"),
            ],
        ),
        (
            "win-mpre8vi4u6u",
            [("10960", "doing", "win-mpre8vi4u6u-10960")],
        ),
    ):
        doc["machines"][mid] = bobreport._empty_machine(mid)
        workers = {}
        wlist = []
        for pid, state, nick in seats:
            workers[pid] = {"state": state, "nick": nick}
            wlist.append({"nick": nick, "state": state, "pid": int(pid)})
        doc["machines"][mid]["workers"] = workers
        doc["machines"][mid]["worker_list"] = wlist
    bobreport.save_digest(digest, doc)


def test_queue_flow_no_starve_when_only_orphans_idle_and_work_offerable_to_busy(
    tmp_path, monkeypatch
):
    """Pre-fix: offerable vs ALL nicks + orphan idle_seat_count => false true starve."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare", "win-mpre8vi4u6u"})
    _write_busy_fleet_with_orphan_idles(digest)
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
                        "task": "MRB",
                        "id": "#1645",
                        "title": "MRB: open PR",
                        "labels": ["feature-request"],
                        "line": "MRB SimonBarnett/bobiverse#1645",
                        "url": "https://github.com/SimonBarnett/bobiverse/pull/1645",
                    },
                ],
                "accepted": [],
                "done": [],
            }
        ),
        encoding="utf-8",
    )

    idle_payload, idle_code = idle_seats.check(_args(chair, digest))
    assert idle_code == 0, idle_payload
    assert idle_payload["offerable_for_live_seats"] == 0
    assert idle_payload["idle_seats"] == []

    qf_payload, qf_code = queue_flow.check(_args(chair, digest))
    assert qf_code == 0, qf_payload
    assert qf_payload["ok"] is True
    assert int(qf_payload.get("ungated_offerable_count") or 0) == 0
    assert int(qf_payload.get("offerable_for_idle_seats") or 0) == 0
    assert int(qf_payload.get("idle_seat_count") or 0) == 0
    assert "true starve" not in " ".join(qf_payload.get("findings") or [])


def test_count_offerable_against_busy_nicks_would_be_nonzero_but_idle_path_is_zero(
    tmp_path, monkeypatch
):
    """Document the bug class: same queue is offerable to a doing nick, not to idle set."""
    chair = tmp_path / ".jeeves"
    digest = tmp_path / ".bobiverse"
    chair.mkdir()
    registered_machines.save_registered(digest, {"marchhare"})
    _write_busy_fleet_with_orphan_idles(digest)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    rows = [
        {
            "repo": "SimonBarnett/bobiverse",
            "task": "MRB",
            "id": "#1645",
            "title": "MRB: open PR",
            "labels": ["feature-request"],
            "line": "MRB SimonBarnett/bobiverse#1645",
            "url": "https://github.com/SimonBarnett/bobiverse/pull/1645",
        }
    ]
    (digest / "queue.json").write_text(
        json.dumps({"v": 1, "unaccepted": rows, "accepted": [], "done": []}),
        encoding="utf-8",
    )
    home = digest
    # Busy nick alone can still see the row as offerable (old queue_flow bug input).
    busy_n = idle_seats.count_offerable_for_live_seats(
        home, rows, ["marchhare-41928", "win-mpre8vi4u6u-10960"]
    )
    idle_n = idle_seats.count_offerable_for_live_seats(home, rows, [])
    orphan_idle = idle_seats.collect_idle_shop_seats(
        (bobreport.load_digest(digest) or {}).get("machines")
    )
    assert busy_n >= 1
    assert idle_n == 0
    assert orphan_idle == []
