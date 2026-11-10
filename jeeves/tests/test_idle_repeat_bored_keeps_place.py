"""FR #6360: a repeat !bored keeps a seat's place in the idle-offer line (told_at)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bobreport
import focus_ignore as fi
import gitclaim
import registered_machines as rm


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#marchhare", "#flamingo", "#win-mpre8vi4u6u"]
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    fi.handle_focus_cmd(tmp_path, "bobiverse")
    return tmp_path


def _queue(home: Path, rows: list[dict]) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {"v": 1, "unaccepted": list(rows), "accepted": [], "done": []},
    )


def _row(task="FR", num=10, seq=1, repo="SimonBarnett/bobiverse", **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-06T10:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/{repo}/issues/{num}",
        "title": f"job {num}",
    }
    r.update(kw)
    return r


def _put_idle_digest(home: Path, *nicks: str) -> None:
    doc = bobreport.load_digest(home)
    machines = doc.setdefault("machines", {})
    by_mid: dict[str, list[str]] = {}
    for nick in nicks:
        parsed = bobreport.parse_seat_nick(nick)
        if not parsed:
            continue
        mid, _pid = parsed
        by_mid.setdefault(mid, []).append(nick)
    for mid, seats in by_mid.items():
        ent = machines.setdefault(mid, {"id": mid, "online": True})
        ent["online"] = True
        ent["worker_list"] = [
            {
                "nick": n,
                "state": "idle",
                "work": "",
                "updated": "2026-10-06T10:00:00Z",
            }
            for n in seats
        ]
        ent["working_on"] = ""
    bobreport.save_digest(home, doc)


def _raw(home: Path) -> dict:
    path = gitclaim.idle_after_empty_path(home)
    if not path.exists():
        return {"v": 1, "seats": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _seed_raw(home: Path, nick: str, row: dict) -> None:
    path = gitclaim.idle_after_empty_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = _raw(home)
    doc.setdefault("seats", {})[nick] = row
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_repeat_bored_keeps_place_and_wins_push(home):
    said = []
    _put_idle_digest(home, "marchhare-1", "flamingo-9")
    t0 = 1000.0
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0)
    gitclaim.note_idle_after_empty(home, "flamingo-9", "#flamingo", now=t0 + 60)
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0 + 120)
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0 + 240)

    raw = _raw(home)
    assert raw["seats"]["marchhare-1"]["told_at"] == t0
    assert raw["seats"]["marchhare-1"]["last_seen"] == t0 + 240

    _queue(home, [_row("FR", 10, 1)])
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=t0 + 300
    )
    assert n == 1
    assert said[0][1].startswith("marchhare-1:")
    assert "marchhare" in str(gitclaim.load_queue(home)["unaccepted"][0]["offered_to"]).lower()


def test_entry_expires_and_repeat_refreshes_expiry(home):
    t0 = 1000.0
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0)
    assert gitclaim.list_idle_after_empty(home, now=t0 + 900, live=set())
    assert gitclaim.list_idle_after_empty(home, now=t0 + 901, live=set()) == []

    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0)
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0 + 600)
    assert gitclaim.list_idle_after_empty(home, now=t0 + 1200, live=set())
    assert gitclaim.list_idle_after_empty(home, now=t0 + 1501, live=set()) == []


def test_reidle_after_offer_resets_told_at(home):
    said = []
    _put_idle_digest(home, "marchhare-1")
    t0 = 1000.0
    t1 = 2000.0
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0)
    _queue(home, [_row("FR", 10, 1)])
    assert (
        gitclaim.offer_to_idle_seats(
            home, say=lambda ch, t: said.append((ch, t)), now=t0 + 1
        )
        == 1
    )
    assert "marchhare-1" not in _raw(home)["seats"]

    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t1)
    raw = _raw(home)["seats"]["marchhare-1"]
    assert raw["told_at"] == t1
    assert raw["last_seen"] == t1


def test_stale_row_without_intervening_list_starts_new_period(home):
    _put_idle_digest(home, "marchhare-1", "flamingo-9")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    gitclaim.note_idle_after_empty(home, "flamingo-9", "#flamingo", now=1500.0)
    # 901 s since A's last_seen and no list call pruned it: registration itself resets.
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1901.0)
    assert _raw(home)["seats"]["marchhare-1"]["told_at"] == 1901.0
    rows = gitclaim.list_idle_after_empty(home, now=1901.0)
    assert [r["nick"] for r in rows] == ["flamingo-9", "marchhare-1"]


def test_last_seen_survives_list_clear_say_false_and_no_job_stamp(home):
    t0 = 1000.0
    _put_idle_digest(home, "marchhare-1", "flamingo-9")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0)
    # A stale sibling is pruned by the list call; A keeps last_seen.
    _seed_raw(
        home,
        "flamingo-9",
        {"nick": "flamingo-9", "channel": "#flamingo", "told_at": 50.0, "last_push_at": 0.0},
    )
    rows = gitclaim.list_idle_after_empty(home, now=t0, live={"marchhare-1", "flamingo-9"})
    assert [r["nick"] for r in rows] == ["marchhare-1"]
    assert _raw(home)["seats"]["marchhare-1"]["last_seen"] == t0

    # Clearing an unrelated seat leaves A's last_seen intact.
    gitclaim.clear_idle_after_empty(home, "flamingo-9")
    assert _raw(home)["seats"]["marchhare-1"]["last_seen"] == t0

    # A failed delivery keeps the idle entry, and last_seen survives the last_push_at stamp.
    _queue(home, [_row("FR", 10, 1)])
    assert (
        gitclaim.offer_to_idle_seats(home, say=lambda ch, t: False, now=t0 + 10) == 0
    )
    assert _raw(home)["seats"]["marchhare-1"]["last_seen"] == t0

    # A no-offerable-job tick also keeps last_seen while stamping last_push_at.
    _queue(home, [])
    gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: True, now=t0 + 100
    )
    raw = _raw(home)["seats"]["marchhare-1"]
    assert raw["last_seen"] == t0
    assert raw["last_push_at"] == t0 + 100


def test_legacy_row_without_last_seen_uses_told_at(home):
    t0 = 1000.0
    _seed_raw(
        home,
        "marchhare-1",
        {"nick": "marchhare-1", "channel": "#marchhare", "told_at": t0, "last_push_at": 0.0},
    )
    assert gitclaim.list_idle_after_empty(home, now=t0 + 900, live=set())
    assert gitclaim.list_idle_after_empty(home, now=t0 + 901, live=set()) == []

    _seed_raw(
        home,
        "marchhare-1",
        {"nick": "marchhare-1", "channel": "#marchhare", "told_at": t0, "last_push_at": 0.0},
    )
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0 + 100)
    raw = _raw(home)["seats"]["marchhare-1"]
    assert raw["told_at"] == t0
    assert raw["last_seen"] == t0 + 100

    _seed_raw(
        home,
        "marchhare-1",
        {
            "nick": "marchhare-1",
            "channel": "#marchhare",
            "told_at": t0,
            "last_push_at": "not-a-number",
        },
    )
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=t0 + 200)
    assert _raw(home)["seats"]["marchhare-1"]["last_push_at"] == 0.0
