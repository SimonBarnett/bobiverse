"""FR #2803: Jeeves pushes new work to seats idle after 'nothing queued' (no wait for next !bored)."""
from __future__ import annotations

import time
from datetime import datetime, timezone
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


def _row(task="MRB", num=200, seq=1, repo="SimonBarnett/bobiverse", **kw):
    r = {
        "repo": repo,
        "task": task,
        "id": f"#{num}",
        "seq": seq,
        "ts": f"2026-10-06T10:00:{seq:02d}Z",
        "line": "x",
        "url": f"https://github.com/{repo}/pull/{num}",
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


def test_idle_seat_new_row_immediate_offer(home):
    """Fails on main before FR #2803: no offer until seat's next !bored."""
    said = []
    _put_idle_digest(home, "marchhare-1")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    _queue(home, [_row("MRB", 200, 1)])
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 1
    assert len(said) == 1
    ch, line = said[0]
    assert ch.lower() == "#marchhare"
    assert line.startswith("marchhare-1: MRB SimonBarnett/bobiverse#200")
    doc = gitclaim.load_queue(home)
    row = doc["unaccepted"][0]
    assert "marchhare" in str(row.get("offered_to") or "").lower()
    assert gitclaim.list_idle_after_empty(home, now=1001.0) == []


def test_self_mrb_respected(home):
    said = []
    _put_idle_digest(home, "marchhare-1", "flamingo-9")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    gitclaim.note_idle_after_empty(home, "flamingo-9", "#flamingo", now=1000.5)
    _queue(
        home,
        [
            _row(
                "MRB",
                200,
                1,
                author_seat="marchhare-1",
                implementer_seat="marchhare-1",
            )
        ],
    )
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 1
    assert len(said) == 1
    assert said[0][1].startswith("flamingo-9:")


def test_focus_respected(home):
    said = []
    _put_idle_digest(home, "marchhare-1")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    fi.handle_unfocus_cmd(home, "all")
    fi.handle_focus_cmd(home, "strict on")
    fi.handle_focus_cmd(home, "SimonBarnett/not-this")
    _queue(
        home,
        [
            _row(
                "FR",
                10,
                1,
                url="https://github.com/SimonBarnett/bobiverse/issues/10",
            )
        ],
    )
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 0
    assert said == []
    idle = gitclaim.list_idle_after_empty(home, now=1001.0)
    assert any("marchhare" in e["nick"] for e in idle)


def test_giveup_cooldown_respected(home):
    said = []
    nick = "marchhare-1"
    _put_idle_digest(home, nick)
    gitclaim.note_idle_after_empty(home, nick, "#marchhare", now=1000.0)
    until = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    row = _row(
        "FR",
        10,
        1,
        giveup_seats=nick,  # comma-list string (gitclaim.giveup_seat_set)
        cooldown_until=until,
        url="https://github.com/SimonBarnett/bobiverse/issues/10",
    )
    _queue(home, [row])
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 0
    assert said == []


def test_busy_seat_no_push(home):
    said = []
    nick = "marchhare-1"
    gitclaim.note_idle_after_empty(home, nick, "#marchhare", now=1000.0)
    _queue(
        home,
        [
            _row(
                "FR",
                10,
                1,
                url="https://github.com/SimonBarnett/bobiverse/issues/10",
            )
        ],
    )
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "working_on": "FR SimonBarnett/bobiverse#9",
        "worker_list": [
            {
                "nick": nick,
                "state": "doing",
                "work": "FR SimonBarnett/bobiverse#9",
                "updated": "2026-10-06T10:00:00Z",
            }
        ],
        "workers": {
            "1": {
                "pid": "1",
                "nick": nick,
                "state": "doing",
                "working_on": "FR SimonBarnett/bobiverse#9",
            }
        },
    }
    bobreport.save_digest(home, doc)
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 0
    assert said == []


def test_stale_idle_entry_removed(home):
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    idle = gitclaim.list_idle_after_empty(
        home, now=1000.0 + gitclaim.IDLE_AFTER_EMPTY_MAX_AGE_S + 1
    )
    assert idle == []


def test_two_idle_seats_one_row_oldest_wins(home):
    said = []
    _put_idle_digest(home, "flamingo-9", "marchhare-1")
    gitclaim.note_idle_after_empty(home, "flamingo-9", "#flamingo", now=1000.0)
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=900.0)
    # FR row must not carry a /pull/ URL or purge_fr_that_are_pulls drops it.
    _queue(
        home,
        [
            _row(
                "FR",
                10,
                1,
                url="https://github.com/SimonBarnett/bobiverse/issues/10",
            )
        ],
    )
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    assert n == 1
    assert len(said) == 1
    assert said[0][1].startswith("marchhare-1:")
    assert not any("nothing queued" in t for _, t in said)


def test_race_bored_and_push_one_assign(home):
    said = []
    nick = "marchhare-1"
    _put_idle_digest(home, nick)
    gitclaim.note_idle_after_empty(home, nick, "#marchhare", now=1000.0)
    _queue(
        home,
        [
            _row(
                "FR",
                10,
                1,
                url="https://github.com/SimonBarnett/bobiverse/issues/10",
            )
        ],
    )
    n = gitclaim.offer_to_idle_seats(
        home, say=lambda ch, t: said.append((ch, t)), now=1001.0
    )
    st, job = gitclaim.offer_focus_top(home, nick, "#marchhare", now=1001.0)
    if st == "ok" and job:
        said.append(("#marchhare", gitclaim.format_assign_line(nick, job)))
    assert n == 1
    assert any("bobiverse#10" in line.lower() for _, line in said)
    doc = gitclaim.load_queue(home)
    assert len(doc["unaccepted"]) == 1


def test_enqueue_unaccepted_triggers_chair_outbox_push(home):
    """Webhook enqueue path writes shop assign into chair-outbox for idle seat."""
    _put_idle_digest(home, "marchhare-1")
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=time.time())
    # Avoid bored_gate wait: activity must be older than IDLE_S.
    gitclaim.note_worker_activity(home, "marchhare-1", time.time() - 10_000)
    claim = gitclaim.GitClaim(
        repo="SimonBarnett/bobiverse",
        task="FR",
        id="#2803",
        event="issues",
        action="opened",
        line="GIT issues opened SimonBarnett/bobiverse#2803",
        title="offer idle",
        body="x",
    )
    result = gitclaim.enqueue_unaccepted(home, claim)
    assert result == "added"
    outbox = bobreport.fleet_digest_home(home) / "chair-outbox.txt"
    text = outbox.read_text(encoding="utf-8") if outbox.exists() else ""
    assert "PRIVMSG #marchhare :" in text
    assert "marchhare-1: FR SimonBarnett/bobiverse#2803" in text


def test_note_idle_cleared_on_explicit_clear(home):
    gitclaim.note_idle_after_empty(home, "marchhare-1", "#marchhare", now=1000.0)
    gitclaim.clear_idle_after_empty(home, "marchhare-1")
    assert gitclaim.list_idle_after_empty(home, now=1000.0) == []
