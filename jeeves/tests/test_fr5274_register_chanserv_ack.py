"""FR #5274: !register ACK only after ChanServ confirms; REGISTERED v1 on success."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from repo_layout import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import registered_machines as rm  # noqa: E402
import unregister_cmd as uc  # noqa: E402
from irc_agent import Client  # noqa: E402


class _FakePriv:
    def __init__(self, members):
        self.state = SimpleNamespace(members=members)


class _FakeArgs:
    chair = True


def _make_agent(tmp_path, members, now=None):
    sent = []
    whispers = []
    clock = {"t": 100.0 if now is None else now}
    agent = SimpleNamespace(
        args=_FakeArgs(),
        home=str(tmp_path),
        channels=["#bobiverse"],
        _unregister_pending=uc.PendingUnregisterStore(),
        _cs_unregister_wait={},
        _cs_register_wait={},
        _cs_force=False,
        _cs_collector=None,
        _privs_engine=_FakePriv(members),
        _mine_nicks=lambda: {"jeeves"},
        _digest_home=lambda: tmp_path,
        send=lambda line: sent.append(line),
        whisper=lambda who, msg: whispers.append((who, msg)),
        _register_now=lambda: clock["t"],
    )
    agent._nick_modes_in_channel = Client._nick_modes_in_channel.__get__(agent, Client)
    agent._register_gate_allowed = Client._register_gate_allowed.__get__(agent, Client)
    agent._handle_register_command = Client._handle_register_command.__get__(agent, Client)
    agent._on_chanserv_notice = Client._on_chanserv_notice.__get__(agent, Client)
    agent._register_wait_s = Client._register_wait_s.__get__(agent, Client)
    agent._register_join_wait_s = Client._register_join_wait_s.__get__(agent, Client)
    agent._chair_present_in_shop = Client._chair_present_in_shop.__get__(agent, Client)
    agent._send_chanserv_register = Client._send_chanserv_register.__get__(agent, Client)
    agent._promote_register_join_wait = Client._promote_register_join_wait.__get__(agent, Client)
    agent._on_register_presence_line = Client._on_register_presence_line.__get__(agent, Client)
    agent._expire_register_waits = Client._expire_register_waits.__get__(agent, Client)
    agent._finish_register_ok = Client._finish_register_ok.__get__(agent, Client)
    agent._finish_register_fail = Client._finish_register_fail.__get__(agent, Client)
    return agent, sent, whispers, clock


def test_fr5274_parse_chanserv_register_result():
    assert uc.parse_chanserv_register_result(
        "Successfully registered channel #redqueen"
    ) == ("ok", "#redqueen")
    assert uc.parse_chanserv_register_result(
        "Channel #redqueen is now registered"
    ) == ("ok", "#redqueen")
    assert uc.parse_chanserv_register_result(
        "Channel #redqueen is already registered"
    ) == ("ok", "#redqueen")
    kind, shop = uc.parse_chanserv_register_result(
        "You must be in the channel to register it"
    )
    assert kind == "fail"
    assert uc.parse_chanserv_register_result("LIST of channels") == ("unknown", None)


def test_fr5274_register_does_not_ack_before_chanserv(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, _ = _make_agent(tmp_path, members)
    assert agent._handle_register_command("simon", "!register redqueen") is True
    assert any(x == "JOIN #redqueen" for x in sent)
    assert not any("REGISTER #redqueen" in x for x in sent)
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!j@h")
    assert any("REGISTER #redqueen" in x for x in sent)
    assert not any(m.startswith("ACK registered") for _, m in whispers)
    assert not rm.is_registered(tmp_path, "redqueen")
    assert "#redqueen" in agent._cs_register_wait


def test_fr5274_register_ack_and_announce_on_chanserv_ok(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, _ = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!j@h")
    agent._on_chanserv_notice("Successfully registered channel #redqueen")
    assert any(m.startswith("ACK registered #redqueen") for _, m in whispers)
    assert any("PRIVMSG #bobiverse :REGISTERED v1 redqueen" in x for x in sent)
    assert rm.is_registered(tmp_path, "redqueen")
    assert agent._cs_force is True
    assert not agent._cs_register_wait


def test_fr5274_register_no_ack_on_chanserv_fail(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"h"}}}}
    agent, sent, whispers, _ = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!j@h")
    agent._on_chanserv_notice("You must be in the channel to register it")
    assert not any(m.startswith("ACK registered") for _, m in whispers)
    assert any("ERR !register" in m and "ChanServ" in m for _, m in whispers)
    assert not rm.is_registered(tmp_path, "redqueen")
    assert not any("REGISTERED v1" in x for x in sent)


def test_fr5274_register_no_ack_on_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, clock = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!j@h")
    clock["t"] = 100.0 + uc.REGISTER_WAIT_S + 1
    agent._expire_register_waits()
    assert not any(m.startswith("ACK registered") for _, m in whispers)
    assert any("timeout" in m.lower() for _, m in whispers)
    assert not rm.is_registered(tmp_path, "redqueen")
    assert not any("REGISTERED v1" in x for x in sent)
