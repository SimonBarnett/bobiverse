"""Hostile MRB #2450: pin+ledger heal must not fire unless ALL matching live seats GIVEUP'd."""
from __future__ import annotations

import json
import time
from pathlib import Path

import gitclaim
import queue_flow
from repo_layout import ROOT


def _digest_seats(home: Path, machines: dict[str, tuple[str, ...]]) -> None:
    seats = {}
    for mid, ports in machines.items():
        seats[mid] = {
            "worker_list": [f"{mid}-{p}" for p in ports],
            "running": len(ports),
        }
    (home / "digest-report.json").write_text(
        json.dumps({"seats": seats, "ts": time.time()}), encoding="utf-8"
    )


def _queue(home: Path, rows: list[dict]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "queue.json").write_text(
        json.dumps({"unaccepted": rows, "accepted": []}), encoding="utf-8"
    )


def _row(repo, task, number, prio, **extra):
    d = {
        "repo": repo,
        "task": task,
        "id": f"#{number}",
        "number": number,
        "priority": prio,
        "title": f"{task} {number}",
        "pull_url": "",
    }
    d.update(extra)
    return d


def test_hostile_partial_giveup_does_not_heal(tmp_path):
    home = tmp_path / "digest"
    home.mkdir()
    _digest_seats(home, {"ionos": ("100", "200")})
    _queue(
        home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "FR",
                1993,
                1,
                require_machine="ionos",
            ),
        ],
    )
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    live = gitclaim.live_seat_nicks(home)
    blocked = gitclaim.require_machine_all_live_gave_up(
        home,
        {
            "repo": "SimonBarnett/bobiverse",
            "id": "#1993",
            "task": "FR",
            "require_machine": "ionos",
        },
        live,
    )
    assert blocked == []
    assert gitclaim.heal_require_machine_all_gave_up(home, live) == []
    assert gitclaim.ledger_clear_giveup(home, "SimonBarnett/bobiverse", "#1993", nick="ionos-100") == 1


def test_hostile_irc_line_stays_short_under_pin_starve(tmp_path):
    home = tmp_path / "digest"
    home.mkdir()
    _digest_seats(home, {"ionos": ("100",), "marchhare": ("1",)})
    _queue(
        home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "FR",
                1993,
                1,
                require_machine="ionos",
            ),
        ],
    )
    gitclaim.ledger_giveup(home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    stats = gitclaim.summarize_empty_offer(home, "marchhare-1")
    line = gitclaim.format_nothing_queued("marchhare-1", stats)
    assert line == "marchhare-1: nothing queued"
    assert "require_machine" not in line
    assert "ledger" not in line


def test_hostile_docs_and_monitor_wiring():
    op = (ROOT / "jeeves" / "docs" / "empty-offer-operator.md").read_text(encoding="utf-8")
    assert "heal_require_machine_all_gave_up" in op
    assert "ledger_clear_giveup" in op
    mon = (ROOT / "jeeves" / "docs" / "monitoring.md").read_text(encoding="utf-8")
    assert "empty-offer-operator.md" in mon
    assert "empty-offer-playbook.md" in mon
    qf = (ROOT / "jeeves" / "tools" / "monitor" / "queue_flow.py").read_text(encoding="utf-8")
    assert "heal_require_machine_all_gave_up" in qf
    assert "EMPTY_OFFER_STARVE_S" in qf
    assert queue_flow.PIN_LEDGER_STARVE_S == queue_flow.EMPTY_OFFER_STARVE_S
