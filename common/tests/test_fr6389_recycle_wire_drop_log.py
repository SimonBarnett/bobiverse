"""FR #6389: ear logs why a routed RECYCLE v1 is dropped; chair case-insensitive; e2e."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import bob_recycle
import bobreport
import irc_agent
import registered_machines as rm

CHANS = ["#bobiverse", "#marchhare", "#flamingo", "#win-mpre8vi4u6u"]


class FakeEar:
    """Minimal bob-* ear binding Client._maybe_execute_recycle_wire."""

    def __init__(self, home: Path, *, nick: str = "Bob-marchhare", chair_mode: bool = False):
        self.args = SimpleNamespace(chair=chair_mode)
        self.home = home
        self.original_nick = nick
        self.live_nick = nick
        self.logs: list[str] = []
        self.announced: list[str] = []
        self.recycled: list[str] = []
        self._recycle_hooks = None

    def _announce_departure(self, reason: str) -> None:
        self.announced.append(reason)

    _maybe_execute_recycle_wire = irc_agent.Client._maybe_execute_recycle_wire
    _local_machine_id = irc_agent.Client._local_machine_id


@pytest.fixture
def ear_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    monkeypatch.setenv("BOB_HOME", str(tmp_path))
    monkeypatch.delenv("BOB_CHAIR_NICK", raising=False)
    monkeypatch.setenv("BOB_CHAIR_MACHINE", "win-mpre8vi4u6u")
    rm.sync_from_chanserv(tmp_path, CHANS)
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    # digest.json chairNick as live MarchHare (capital J)
    bobreport.save_digest(tmp_path, {"chairNick": "Jeeves", "machines": {}})
    return tmp_path


def _patch_info(ear, monkeypatch):
    monkeypatch.setattr(irc_agent, "info", lambda m: ear.logs.append(m))
    monkeypatch.setattr(
        bob_recycle,
        "execute_local_recycle",
        lambda mid, home, **k: ear.recycled.append(mid),
    )


def test_fr6389_chair_nick_case_insensitive_jeeves(ear_home, monkeypatch):
    """chairNick 'Jeeves' accepts sender 'jeeves' (MarchHare silent-drop class)."""
    ear = FakeEar(ear_home)
    _patch_info(ear, monkeypatch)
    ok = ear._maybe_execute_recycle_wire("jeeves", "RECYCLE v1 marchhare")
    assert ok is True
    assert ear.recycled == ["marchhare"]
    assert ear.announced == ["recycle"]
    assert any("recycle wire accepted" in m for m in ear.logs)
    assert not any("recycle wire dropped" in m for m in ear.logs)


@pytest.mark.parametrize(
    "reason,setup,src,body",
    [
        (
            "is_chair",
            lambda e, h: setattr(e, "args", SimpleNamespace(chair=True)),
            "jeeves",
            "RECYCLE v1 marchhare",
        ),
        (
            "not_fleet_bob",
            lambda e, h: setattr(e, "original_nick", "marchhare-1234"),
            "jeeves",
            "RECYCLE v1 marchhare",
        ),
        (
            "no_local_machine",
            lambda e, h: setattr(e, "original_nick", "Bob-"),
            "jeeves",
            "RECYCLE v1 marchhare",
        ),
        (
            "machine_mismatch",
            lambda e, h: None,
            "jeeves",
            "RECYCLE v1 flamingo",
        ),
        (
            "chair_mismatch",
            lambda e, h: None,
            "not-jeeves",
            "RECYCLE v1 marchhare",
        ),
        (
            "chair_missing",
            lambda e, h: bobreport.save_digest(h, {"machines": {}}),
            "jeeves",
            "RECYCLE v1 marchhare",
        ),
        (
            "not_recycle_wire",
            lambda e, h: None,
            "jeeves",
            "RECYCLE garbled nonsense",
        ),
    ],
)
def test_fr6389_drop_reason_logged(ear_home, monkeypatch, reason, setup, src, body):
    ear = FakeEar(ear_home)
    _patch_info(ear, monkeypatch)
    setup(ear, ear_home)
    ok = ear._maybe_execute_recycle_wire(src, body)
    assert ok is False
    assert ear.recycled == []
    hits = [m for m in ear.logs if "recycle wire dropped" in m and f"reason={reason}" in m]
    assert hits, ear.logs
    line = hits[0]
    assert "from=" in line and "chair=" in line and "machine=" in line


def test_fr6389_non_recycle_chat_does_not_log_drop(ear_home, monkeypatch):
    """Ordinary PRIVMSG must not flood drop logs."""
    ear = FakeEar(ear_home)
    _patch_info(ear, monkeypatch)
    assert ear._maybe_execute_recycle_wire("someone", "hello shop") is False
    assert not any("recycle wire dropped" in m for m in ear.logs)


def test_fr6389_e2e_chair_routes_ear_recycles_once(ear_home, monkeypatch):
    """Authorised !recycle <machine> produces wire; matching ear runs execute_local_recycle once."""
    import chair_commands as cc
    import gitclaim
    import time

    # --- chair side (pattern from test_chair_commands_020) ---
    monkeypatch.setenv("JEEVES_OWNER_ACCOUNT", "simon")
    for k in ("JEEVES_FOCUS_MUTATORS", "JEEVES_FOCUS_MUTATOR_ACCOUNTS", "BOB_OP_ACCOUNTS"):
        monkeypatch.delenv(k, raising=False)

    class FakeChair:
        def __init__(self, home):
            self.args = SimpleNamespace(chair=True)
            self.home = home
            self.live_nick = self.original_nick = "Jeeves"
            self.channels = list(CHANS)
            self.sent, self.pms, self.said, self.logs = [], [], [], []
            self.joined = SimpleNamespace(is_set=lambda: True)
            self._chan_op = {c: True for c in CHANS}
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

        def _maybe_channel_pong(self, *a):
            return False

        def _maybe_shop_listen(self, *a):
            return False

        def _maybe_git_claim(self, *a):
            return False

        def _handle_register_command(self, *a):
            return False

        def _handle_unregister_command(self, *a):
            return False

        def _handle_build_command(self, *a):
            return None

        def _handle_installtest_command(self, *a):
            return None

        def _mark_pm_open(self, n):
            pass

        def _is_briefer(self):
            return False

        def _refresh_ledger(self):
            pass

        for _n in (
            "handle_privmsg",
            "_maybe_chair_commands",
            "_maybe_git_list",
            "_maybe_git_help",
            "_maybe_focus_ignore",
            "_maybe_assign",
            "_git_say",
            "_handle_recycle_command",
            "_handle_bob_local_recycle_command",
            "_maybe_startworker",
            "_maybe_recycleseat",
            "_maybe_cleargiveup",
            "_cc",
            "_ear_machine",
            "_account_of",
            "_principal",
            "_jobs",
            "_jobs_status_lines",
            "_whois_hint",
            "_cmd_trace",
            "_cmd_reply",
            "_privs",
            "_privs_skip_whois",
            "_on_channel_names",
            "_workers",
            "_maybe_execute_recycle_wire",
            "_maybe_consume_installtest_v1_wire",
            "_maybe_consume_build_v1_wire",
        ):
            locals()[_n] = getattr(irc_agent.Client, _n)
        del _n

    chair = FakeChair(ear_home)
    monkeypatch.setattr(irc_agent, "info", lambda m: chair.logs.append(m))
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        bob_recycle,
        "execute_local_recycle",
        lambda mid, home, **k: chair.recycled.append(("chair", mid)),
    )
    import agent_control

    monkeypatch.setattr(agent_control, "request_agent_quit", lambda *a, **k: None)
    gitclaim._write_queue(
        gitclaim.queue_path(ear_home),
        {"v": 1, "accepted": [], "unaccepted": []},
    )
    # Owner op for !recycle
    chair.acct["simon"] = "simon"
    # Force principal: mark sender as owner via account
    from irc_agent import Client

    # Use chair command path like test_chair_commands_020
    op = "Bob-win-mpre8vi4u6u"
    chair.acct[op.lower()] = "simon"
    # Also allow via _privs: ear nick with account simon is owner
    Client.handle_privmsg(chair, op, "#bobiverse", "!recycle marchhare")
    wires = [s for s in chair.sent if "RECYCLE v1 marchhare" in s]
    assert wires, (chair.sent, chair.pms, chair.logs)
    body = wires[0].split(" :", 1)[1]

    # --- ear side consumes the same wire ---
    ear = FakeEar(ear_home)
    ear_calls: list[str] = []

    def _exec(mid, home, **k):
        ear_calls.append(mid)

    monkeypatch.setattr(bob_recycle, "execute_local_recycle", _exec)
    monkeypatch.setattr(irc_agent, "info", lambda m: ear.logs.append(m))
    assert ear._maybe_execute_recycle_wire("jeeves", body) is True
    assert ear_calls == ["marchhare"]
    assert ear.announced == ["recycle"]
    assert any("recycle announcing restart" in m for m in ear.logs)
    assert any("recycle wire accepted" in m for m in ear.logs)


def test_fr6389_parse_recycle_command_does_not_eat_wire():
    """PRIVMSG dispatch: !recycle parser must not consume RECYCLE v1 bodies."""
    import bobtalk

    assert bobtalk.parse_recycle_command("RECYCLE v1 marchhare") is False
    assert bobtalk.parse_recycle_command("!recycle marchhare") is True
