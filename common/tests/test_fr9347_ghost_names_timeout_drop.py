"""FR #9347: NAMES miss / shop-presence refuse drops ghost from offer roster."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import bobreport
import gitclaim
import irc_agent
import registered_machines as rm

MH = "marchhare"
SEAT = "marchhare-14168"
GHOST = "marchhare-99999"


def _roster(home: Path) -> None:
    (home / "registered-machines.json").write_text(
        '{"v":1,"machines":["marchhare"]}',
        encoding="utf-8",
    )
    bobreport._SEAT_ROSTER_CACHE["key"] = None


def _digest_with_ghost(home: Path) -> None:
    doc = bobreport.empty_digest()
    doc["machines"]["marchhare"] = {
        "id": "marchhare",
        "online": True,
        "workers": {},
        "worker_list": [
            {
                "nick": GHOST,
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T13:00:00Z",
            },
            {
                "nick": SEAT,
                "state": "idle",
                "work": "",
                "updated": "2026-11-23T13:00:00Z",
            },
        ],
        "shop_members_ts": "2026-11-23T12:00:00Z",
    }
    bobreport.save_digest(home, doc)


def test_fr9347_drop_ghost_removes_worker_list_and_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    _roster(tmp_path)
    _digest_with_ghost(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "id": "#9338",
                    "number": "9338",
                    "offered_to": GHOST,
                    "offered_ts": "2026-11-23T13:01:00Z",
                    "offered_channel": "#marchhare",
                    "title": "ghost offer",
                    "labels": [],
                    "line": "MRB SimonBarnett/bobiverse#9338",
                }
            ],
            "accepted": [],
            "done": [],
        },
    )

    out = gitclaim.drop_ghost_seat_after_names_miss(
        tmp_path, GHOST, reason="NAMES timeout"
    )
    assert out.get("removed") is True
    live = gitclaim.live_seat_nicks(tmp_path)
    assert GHOST not in live
    assert SEAT in live
    doc = gitclaim.load_queue(tmp_path)
    row = doc["unaccepted"][0]
    assert not str(row.get("offered_to") or "").strip()
    assert int(out.get("released_offers") or 0) >= 1


def test_fr9347_expire_pending_names_drops_ghost(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_ASSIGN_NAMES_WAIT_S", "0.01")
    _roster(tmp_path)
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    _digest_with_ghost(tmp_path)
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )

    class ExpireChair:
        def __init__(self, home):
            self.args = SimpleNamespace(chair=True)
            self.home = home
            self.pms = []
            self.logs = []
            self._pending_names_assign = {
                "#marchhare": {
                    "src": "simon",
                    "wnick": GHOST,
                    "repo": "SimonBarnett/bobiverse",
                    "task": "MRB",
                    "ident": "#9338",
                    "deadline": 0.0,
                }
            }

        def _cmd_reply(self, src, kind, lines):
            for line in lines:
                self.pms.append((src, line))

        def _whois_hint(self, src):
            pass

        def _account_of(self, src):
            return None

        def _ear_machine(self, n):
            return None

        def _principal(self, src):
            return SimpleNamespace(ops=True, kind="ops")

        def _workers(self):
            import chan_workers

            return chan_workers.WorkerTracker(
                self.home, log=lambda m: self.logs.append(m)
            )

        _expire_pending_names_assign = irc_agent.Client._expire_pending_names_assign
        _finish_assign_result = irc_agent.Client._finish_assign_result
        _cmd_trace = lambda self, *a, **k: None  # noqa: E731

    monkeypatch.setattr(irc_agent, "info", lambda m: None)
    chair = ExpireChair(tmp_path)
    chair._expire_pending_names_assign()
    assert not chair._pending_names_assign
    live = gitclaim.live_seat_nicks(tmp_path)
    assert GHOST not in live
    assert SEAT in live
    assert any("NAMES timeout" in t for _, t in chair.pms)
