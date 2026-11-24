"""FR #9784: after !recycle, clear offered/held + digest ghosts; no assign to recycled nicks."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bobreport
import gitclaim
import irc_agent
import registered_machines as rm


NOW = 1_700_000_000.0
MID = "redqueen"
NICK_A = "redqueen-11500"
NICK_B = "redqueen-11944"
REPO = "SimonBarnett/bobiverse"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        json.dumps({"v": 1, "machines": [MID, "marchhare", "flamingo"]}),
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_with_ghosts(home: Path) -> None:
    _roster(home)
    doc = bobreport.empty_digest()
    doc["machines"][MID] = {
        "id": MID,
        "online": True,
        "workers": {
            "11500": {"pid": "11500", "state": "idle", "nick": NICK_A},
            "11944": {"pid": "11944", "state": "doing", "nick": NICK_B, "working_on": "MRB #9737"},
        },
        "worker_list": [
            {
                "nick": NICK_A,
                "state": "idle",
                "work": "",
                "updated": "2026-11-24T18:20:00Z",
            },
            {
                "nick": NICK_B,
                "state": "doing",
                "work": "MRB #9737",
                "updated": "2026-11-24T18:20:00Z",
            },
        ],
        "workers_last_good": [
            {"nick": NICK_A, "state": "idle", "work": "", "updated": "2026-11-24T18:20:00Z"},
        ],
        "workers_last_good_at": "2026-11-24T18:20:00Z",
    }
    bobreport.save_digest(home, doc)


def _queue_sticky(home: Path) -> None:
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#9737",
                    "title": "t",
                    "url": f"https://github.com/{REPO}/pull/9737",
                    "offered_to": NICK_A,
                    "offered_ts": "2026-11-24T18:24:00Z",
                    "offered_channel": f"#{MID}",
                    "offered_via": "offer",
                }
            ],
            "accepted": [
                {
                    "repo": REPO,
                    "task": "MRB",
                    "id": "#9731",
                    "title": "t",
                    "url": f"https://github.com/{REPO}/pull/9731",
                    "nick": NICK_B,
                    "accepted_ts": NOW,
                }
            ],
            "done": [],
        },
    )
    gitclaim.note_seat_hold(
        home,
        NICK_A,
        {"repo": REPO, "task": "MRB", "id": "#9737"},
        via="offer",
    )


def test_fr9784_clear_machine_workers_wipes_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _digest_with_ghosts(tmp_path)
    assert NICK_A in gitclaim.live_seat_nicks(tmp_path)
    out = bobreport.clear_machine_workers_after_recycle(tmp_path, MID)
    assert out.get("cleared") is True
    ent = bobreport.load_digest(tmp_path)["machines"][MID]
    assert not list(ent.get("worker_list") or [])
    assert not (ent.get("workers") or {})
    assert not ent.get("workers_last_good")
    assert NICK_A not in gitclaim.live_seat_nicks(tmp_path)
    assert NICK_B not in gitclaim.live_seat_nicks(tmp_path)


def test_fr9784_clear_queue_frees_offered_accepted_holds(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    _digest_with_ghosts(tmp_path)
    _queue_sticky(tmp_path)
    out = gitclaim.clear_queue_after_machine_recycle(tmp_path, MID)
    assert int(out.get("cleared_offers") or 0) >= 1
    assert int(out.get("released_accepted") or 0) >= 1
    doc = gitclaim.load_queue(tmp_path)
    un = doc["unaccepted"]
    assert all(not str(r.get("offered_to") or "").strip() for r in un)
    # accepted row for recycled nick returned to unaccepted (no giveup stamp)
    assert not any(
        str(r.get("nick") or "").lower() == NICK_B.lower() for r in doc.get("accepted") or []
    )
    assert any(
        str(r.get("id") or "").endswith("9731") and not str(r.get("nick") or "").strip()
        for r in doc.get("unaccepted") or []
    )
    assert not gitclaim.seat_open_job(tmp_path, NICK_A)


def test_fr9784_recycle_command_clears_ghosts_and_offers(tmp_path, monkeypatch):
    """Fixture: recycle machine with sticky offered nick → no live ghosts; row freed."""
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "win-mpre8vi4u6u")
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS", "BOB_OP_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)
    rm.sync_from_chanserv(
        tmp_path, ["#bobiverse", "#redqueen", "#marchhare", "#win-mpre8vi4u6u"]
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    _digest_with_ghosts(tmp_path)
    _queue_sticky(tmp_path)

    class FakeChair:
        def __init__(self, home):
            self.args = SimpleNamespace(chair=True)
            self.home = home
            self.live_nick = self.original_nick = "Jeeves"
            self.channels = ["#bobiverse", "#redqueen", "#marchhare", "#win-mpre8vi4u6u"]
            self.sent, self.pms, self.said, self.logs = [], [], [], []
            self.joined = SimpleNamespace(is_set=lambda: True)
            self._chan_op = {c: True for c in self.channels}
            self._op_try_at = {}
            self._oper_state = "off"
            self._cs_force = False
            self.acct = {"simon": "simon"}
            self.accounts = SimpleNamespace(get=lambda n: self.acct.get((n or "").lower()))
            self._digest_asm = SimpleNamespace(feed=lambda s, b: None)
            self.recycled = []

        def send(self, line):
            self.sent.append(line)

        def whisper(self, nick, msg):
            self.pms.append((nick, msg))

        def say(self, msg):
            self.said.append(msg)

        def _digest_home(self):
            return self.home

        def _joined_channel(self, t):
            return t.lower() in {c.lower() for c in self.channels}

        def _mine_nicks(self):
            return {"jeeves"}

        def _note_call_channel(self, t):
            pass

        def _mark_pm_open(self, n):
            pass

        def _is_briefer(self):
            return False

        def _refresh_ledger(self):
            pass

        def _whois_hint(self, who):
            pass

        def to(self, nick):
            return [m for n, m in self.pms if n.lower() == nick.lower()]

    for _n in (
        "handle_privmsg",
        "_maybe_chair_commands",
        "_handle_recycle_command",
        "_cc",
        "_ear_machine",
        "_account_of",
        "_principal",
        "_privs",
        "_privs_skip_whois",
        "_cmd_trace",
        "_cmd_reply",
    ):
        setattr(FakeChair, _n, getattr(irc_agent.Client, _n))

    chair = FakeChair(tmp_path)
    monkeypatch.setattr(irc_agent, "info", lambda m: chair.logs.append(m))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        irc_agent.bob_recycle,
        "chair_targets_local",
        lambda mid: False,
    )
    monkeypatch.setattr(
        irc_agent.bob_recycle,
        "execute_local_recycle",
        lambda *a, **k: chair.recycled.append(a[0] if a else "x"),
    )

    irc_agent.Client._handle_recycle_command(chair, "simon", "!recycle redqueen")
    assert any("RECYCLE v1 redqueen" in s for s in chair.sent), chair.sent

    # Digest ghosts gone — live_seat_nicks must not list pre-recycle PIDs.
    live = gitclaim.live_seat_nicks(tmp_path)
    assert NICK_A not in live and NICK_B not in live

    doc = gitclaim.load_queue(tmp_path)
    assert all(not str(r.get("offered_to") or "").strip() for r in doc.get("unaccepted") or [])
    assert not any(
        str(r.get("nick") or "").lower() in {NICK_A.lower(), NICK_B.lower()}
        for r in doc.get("accepted") or []
    )


def test_fr9784_dry_run_does_not_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    _digest_with_ghosts(tmp_path)
    _queue_sticky(tmp_path)
    # dry-run helper path: clear functions not called — simulate by only checking
    # that decide_recycle dry_run leaves digest alone (chair path returns early).
    import chair_commands as cc

    who = cc.Principal(nick="simon", kind="owner", account="simon")
    gate = cc.RecycleGate()
    dec = cc.decide_recycle(
        who=who,
        arg="redqueen",
        dry_run=True,
        roster=(MID, "marchhare"),
        resolve=lambda t: (MID if t == MID else None),
        gate=gate,
    )
    assert dec.ok and dec.dry_run
    assert NICK_A in gitclaim.live_seat_nicks(tmp_path)
    assert str(gitclaim.load_queue(tmp_path)["unaccepted"][0].get("offered_to")) == NICK_A
