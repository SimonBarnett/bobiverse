"""FR #7186: shop presence is NAMES/JOIN/PART, not !bored."""
from __future__ import annotations

from types import SimpleNamespace

import bobreport
import chan_workers
import gitclaim
import irc_agent
import registered_machines as rm

MH = "marchhare"
SEAT = "marchhare-14168"
OTHER = "marchhare-102"


class FakeChair:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.live_nick = "Jeeves"
        self.original_nick = "Jeeves"
        self.channels = ["#bobiverse", "#marchhare"]
        self.sent, self.said, self.logs = [], [], []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._chan_op = {c: True for c in self.channels}
        self._op_try_at = {}
        self._oper_state = "off"
        self.accounts = None

    def send(self, line):
        self.sent.append(line)

    def _digest_home(self):
        return self.home

    def _joined_channel(self, target):
        return target.lower() in {c.lower() for c in self.channels}

    def _git_say(self, target, text):
        self.said.append((target, text))

    def _fleet_moot_state(self):
        return {}

    def _mine_nicks(self):
        return {"jeeves"}

    def _note_call_channel(self, target):
        pass

    _workers = irc_agent.Client._workers
    _privs = irc_agent.Client._privs
    _privs_skip_whois = irc_agent.Client._privs_skip_whois
    _on_channel_names = irc_agent.Client._on_channel_names
    _chair_wire = irc_agent.Client._chair_wire
    _clear_channel_console_presence = irc_agent.Client._clear_channel_console_presence
    _maybe_git_claim = irc_agent.Client._maybe_git_claim
    _maybe_shop_listen = irc_agent.Client._maybe_shop_listen
    def _refresh_ledger(self):
        pass
    _git_bored = irc_agent.Client._git_bored
    _git_ack = irc_agent.Client._git_ack
    _git_accept = irc_agent.Client._git_accept
    _maybe_grant_bob_modes = irc_agent.Client._maybe_grant_bob_modes
    _chan_privs_tick = irc_agent.Client._chan_privs_tick


def _chair(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    gitclaim._write_queue(
        gitclaim.queue_path(tmp_path),
        {"v": 1, "unaccepted": [], "accepted": [], "done": []},
    )
    c = FakeChair(tmp_path)
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    return c


def listed(home, mid=MH):
    ent = bobreport.build_digest_object(home, "J")["machines"].get(mid) or {}
    rows = ent.get("workers") or bobreport._coerce_worker_list(ent.get("worker_list"))
    return [w["nick"] for w in rows]


def wire(chair, line):
    tags, rest = {}, line
    prefix = ""
    if rest.startswith(":"):
        prefix, _, rest = rest[1:].partition(" ")
    parts = rest.split(" ")
    trailing = rest.split(" :", 1)[1] if " :" in rest else ""
    chair._chair_wire(parts[0], parts, trailing, prefix, tags)


def _queue_fr(home, num=7179):
    gitclaim._write_queue(
        gitclaim.queue_path(home),
        {
            "v": 1,
            "unaccepted": [
                {
                    "repo": "SimonBarnett/bobiverse",
                    "task": "FR",
                    "id": f"#{num}",
                    "seq": 1,
                    "ts": "2026-11-14T13:10:50Z",
                    "line": "GIT issues opened",
                    "url": f"https://github.com/SimonBarnett/bobiverse/issues/{num}",
                    "title": f"fr {num}",
                    "labels": ["feature-request"],
                }
            ],
            "accepted": [],
            "done": [],
        },
    )


def test_join_without_bored_lists_seat(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    wire(chair, f":{SEAT}!u@h JOIN #marchhare")
    assert SEAT in listed(chair.home)
    _queue_fr(chair.home)
    st, job = gitclaim.assign_row(
        chair.home, SEAT, "SimonBarnett/bobiverse", "FR", "#7179", issue_open=lambda *_: True
    )
    assert st == "ok"
    assert isinstance(job, dict)


def test_names_adds_missed_join_before_assign_refuse(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    _queue_fr(chair.home)
    wire(chair, f":{OTHER}!u@h JOIN #marchhare")
    doc = bobreport.load_digest(chair.home)
    # OTHER is present; SEAT is not until NAMES refresh.
    assert OTHER in listed(chair.home)
    assert SEAT not in listed(chair.home)
    st, why = gitclaim.assign_row(
        chair.home, SEAT, "SimonBarnett/bobiverse", "FR", "#7179", issue_open=lambda *_: True
    )
    assert st == "refused"

    def _refresh(shop):
        assert shop.lower() == "#marchhare"
        wire(
            chair,
            f":srv 353 Jeeves = #marchhare :@Jeeves +bob-marchhare {SEAT} {OTHER}",
        )
        wire(chair, ":srv 366 Jeeves #marchhare :End of /NAMES list.")

    st, job = gitclaim.assign_row(
        chair.home,
        SEAT,
        "SimonBarnett/bobiverse",
        "FR",
        "#7179",
        issue_open=lambda *_: True,
        names_refresh=_refresh,
    )
    assert st == "ok"
    assert SEAT in listed(chair.home)


def test_part_and_quit_remove_join_only_seat(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    wire(chair, f":{SEAT}!u@h JOIN #marchhare")
    wire(chair, f":{OTHER}!u@h JOIN #marchhare")
    wire(chair, f":{SEAT}!u@h PART #marchhare :bye")
    assert SEAT not in listed(chair.home)
    assert OTHER in listed(chair.home)
    wire(chair, f":{OTHER}!u@h QUIT :Ping timeout")
    assert OTHER not in listed(chair.home)


def test_nick_change_follows_seat(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    wire(chair, f":{SEAT}!u@h JOIN #marchhare")
    wire(chair, f":{SEAT}!u@h NICK :marchhare-999")
    nicks = listed(chair.home)
    assert SEAT not in nicks
    assert "marchhare-999" in nicks


def test_assign_refuse_reason_includes_membership_snapshot(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    _queue_fr(chair.home)
    wire(chair, f":{OTHER}!u@h JOIN #marchhare")
    st, why = gitclaim.assign_row(
        chair.home, SEAT, "SimonBarnett/bobiverse", "FR", "#7179", issue_open=lambda *_: True
    )
    assert st == "refused"
    text = str(why).lower()
    assert "not in the shop channel" in text
    assert "members_at=" in text
    assert "bored" not in text


def test_docs_pin():
    from repo_layout import ROOT

    skill = (ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "FR #7186" in skill
    src = (ROOT / "common" / "scripts" / "chan_workers.py").read_text(encoding="utf-8")
    assert "on_join" in src
    assert "FR #7186" in src
