"""FR #2446 / #2448 / #2449: empty-offer require_machine+ledger breakdown, heal, IRC short line."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bobreport
import gitclaim
import pytest
import registered_machines

ROOT = Path(__file__).resolve().parents[2]
MON = ROOT / "jeeves" / "tools" / "monitor"
if str(MON) not in sys.path:
    sys.path.insert(0, str(MON))
import queue_flow  # noqa: E402


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    registered_machines.save_registered(
        tmp_path, {"ionos", "ce-priority-dev1", "marchhare", "flamingo", "win-mpre8vi4u6u"}
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    return tmp_path


def _row(repo, task, num, seq, **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-01T10:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/{repo}/issues/{num}",
    }
    r.update(kw)
    return r


def _queue(home, rows):
    gitclaim._write_queue(
        gitclaim.queue_path(home), {"v": 1, "unaccepted": rows, "accepted": []}
    )


def _digest_seats(home, machines_pids: dict[str, tuple[str, ...]]):
    doc = bobreport.empty_digest()
    for mid, pids in machines_pids.items():
        doc["machines"][mid] = bobreport._empty_machine(mid)
        doc["machines"][mid]["workers"] = {p: {"state": "idle"} for p in pids}
        doc["machines"][mid]["worker_list"] = [
            {"nick": f"{mid}-{p}", "state": "idle"} for p in pids
        ]
    bobreport.save_digest(home, doc)


def test_fr2446_irc_nothing_queued_stays_short():
    assert (
        gitclaim.format_nothing_queued(
            "marchhare-1",
            {"unaccepted": 3, "require_machine": 2, "ledger": 1, "offerable": 0},
        )
        == "marchhare-1: nothing queued"
    )


def test_fr2446_empty_offer_breakdown_counts_require_machine_and_ledger(_home):
    _digest_seats(_home, {"ionos": ("100", "200"), "marchhare": ("40208",)})
    _queue(
        _home,
        [
            _row(
                "SimonBarnett/bobiverse",
                "FR",
                1993,
                1,
                require_machine="ionos",
            ),
            _row(
                "SimonBarnett/bobiverse",
                "FR",
                1102,
                2,
                require_machine="ce-priority-dev1",
            ),
        ],
    )
    gitclaim.ledger_giveup(_home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    gitclaim.ledger_giveup(_home, "ionos-200", "SimonBarnett/bobiverse", "FR", "#1993")

    stats_mh = gitclaim.summarize_empty_offer(_home, "marchhare-40208")
    assert stats_mh["unaccepted"] == 2
    assert stats_mh["require_machine"] >= 1
    assert stats_mh["offerable"] == 0

    stats_io = gitclaim.summarize_empty_offer(_home, "ionos-100")
    assert stats_io["ledger"] >= 1
    detail = gitclaim.format_empty_offer_detail("ionos-100", stats_io)
    assert "require_machine" in detail
    assert "ledger=" in detail
    assert "offerable for you under focus" in detail


def test_fr2446_heal_clears_when_all_pin_seats_gave_up(_home):
    _digest_seats(_home, {"ionos": ("100", "200")})
    _queue(
        _home,
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
    gitclaim.ledger_giveup(_home, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")
    gitclaim.ledger_giveup(_home, "ionos-200", "SimonBarnett/bobiverse", "FR", "#1993")
    live = gitclaim.live_seat_nicks(_home)
    blocked = gitclaim.require_machine_all_live_gave_up(
        _home,
        {"repo": "SimonBarnett/bobiverse", "id": "#1993", "task": "FR", "require_machine": "ionos"},
        live,
    )
    assert set(blocked) == {"ionos-100", "ionos-200"}
    healed = gitclaim.heal_require_machine_all_gave_up(_home, live)
    assert healed
    assert gitclaim.ledger_clear_giveup(_home, "SimonBarnett/bobiverse", "#1993") == 0
    blocked2 = gitclaim.require_machine_all_live_gave_up(
        _home,
        {"repo": "SimonBarnett/bobiverse", "id": "#1993", "task": "FR", "require_machine": "ionos"},
        live,
    )
    assert blocked2 == []


def test_fr2446_queue_flow_heals_and_empty_timer(tmp_path, monkeypatch, _home):
    monkeypatch.setattr(queue_flow, "PIN_LEDGER_STARVE_S", 1)
    chair = tmp_path / "chair"
    digest = tmp_path
    chair.mkdir(exist_ok=True)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(digest))
    monkeypatch.setenv("JEEVES_HOME", str(chair))
    _digest_seats(digest, {"ionos": ("100",), "marchhare": ("1",)})
    _queue(
        digest,
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
    gitclaim.ledger_giveup(digest, "ionos-100", "SimonBarnett/bobiverse", "FR", "#1993")

    class Args:
        chair_home = str(chair)
        digest_home = str(digest)

    args = Args()
    result, _code = queue_flow.check(args)
    blob = " ".join((result.get("findings") or []) + (result.get("notes") or []))
    assert "pin ledger starve" in blob
    ops = Path(result["ops_home"])
    over, age = queue_flow._update_pin_starve_timer(
        ops, ["empty_offerable unaccepted=1 idle=1"]
    )
    assert over is False
    # Age the FR #2448 EMPTY_OFFER state past threshold (compat timer delegates here).
    state = ops / queue_flow.EMPTY_OFFER_STATE
    doc = json.loads(state.read_text(encoding="utf-8"))
    doc["since"] = time.time() - 120
    state.write_text(json.dumps(doc), encoding="utf-8")
    over2, age2 = queue_flow._update_pin_starve_timer(
        ops, ["empty_offerable unaccepted=1 idle=1"]
    )
    assert over2 is True
    assert age2 >= 100
