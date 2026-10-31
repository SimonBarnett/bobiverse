"""FR #5349: wait for JOIN echo (and optional +o) before ChanServ REGISTER."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

from test_fr5274_register_chanserv_ack import _make_agent

IRC = ROOT / "common" / "scripts" / "irc_agent.py"
TEST = Path(__file__)


def test_fr5349_register_waits_for_join_echo(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, _ = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    assert any(x == "JOIN #redqueen" for x in sent)
    assert not any("PRIVMSG ChanServ :REGISTER" in x for x in sent)
    assert agent._cs_register_wait["#redqueen"]["phase"] == "join"
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!u@h")
    assert any("PRIVMSG ChanServ :REGISTER #redqueen" in x for x in sent)
    assert agent._cs_register_wait["#redqueen"]["phase"] == "register"
    assert not whispers


def test_fr5349_register_promotes_on_366_or_op(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, _, _ = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    agent._on_register_presence_line("366", ["366", "Jeeves", "#redqueen"], "End", "")
    assert any("PRIVMSG ChanServ :REGISTER #redqueen" in x for x in sent)

    agent2, sent2, _, _ = _make_agent(tmp_path, members)
    agent2._handle_register_command("simon", "!register flamingo")
    agent2._on_register_presence_line("MODE", ["MODE", "#flamingo", "+o", "Jeeves"], "", "ChanServ!c@h")
    assert any("PRIVMSG ChanServ :REGISTER #flamingo" in x for x in sent2)


def test_fr5349_already_present_sends_register(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {
        "#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}},
        "#redqueen": {"jeeves": {"nick": "Jeeves", "modes": {"o"}}},
    }
    agent, sent, _, _ = _make_agent(tmp_path, members)
    agent.channels.append("#redqueen")
    agent._handle_register_command("simon", "!register redqueen")
    assert any("PRIVMSG ChanServ :REGISTER #redqueen" in x for x in sent)
    assert agent._cs_register_wait["#redqueen"]["phase"] == "register"


def test_fr5349_join_timeout_fails_in_shop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, clock = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    clock["t"] = 100.0 + 16.0
    agent._expire_register_waits()
    assert any("timeout" in m.lower() and "JOIN" in m for _, m in whispers)
    assert any(x.startswith("PRIVMSG #redqueen :ERR !register") for x in sent)
    assert not any("PRIVMSG ChanServ :REGISTER" in x for x in sent)


def test_fr5349_fail_notice_also_in_shop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("irc_agent.time.sleep", lambda s: None)
    members = {"#bobiverse": {"simon": {"nick": "simon", "modes": {"o"}}}}
    agent, sent, whispers, _ = _make_agent(tmp_path, members)
    agent._handle_register_command("simon", "!register redqueen")
    agent._on_register_presence_line("JOIN", ["JOIN", "#redqueen"], "", "Jeeves!u@h")
    agent._on_chanserv_notice("You must be in the channel to register it")
    assert any("ERR !register" in m for _, m in whispers)
    assert any(x.startswith("PRIVMSG #redqueen :ERR !register") for x in sent)


def test_fr5349_pins_utf8():
    irc = IRC.read_text(encoding="utf-8")
    t = TEST.read_text(encoding="utf-8")
    assert "FR #5349" in irc
    assert "_on_register_presence_line" in irc
    assert "phase" in irc
    assert "BOB_CHANSERV_REGISTER_JOIN_WAIT_S" in irc
    assert "test_fr5349_register_waits_for_join_echo" in t
    assert not IRC.read_bytes().startswith(b"\xef\xbb\xbf")
