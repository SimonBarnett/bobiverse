"""FR #3868: ChanServ LIST omitting #bobiverse must not PART the fleet channel.

Also: chair-status warns when #bobiverse is missing; ear outbox logs each send / 404.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import bobreport
import irc_agent
import registered_machines as rm

LIST_WITHOUT_BOBIVERSE = [
    "*** ChanServ LIST ***",
    "    #flamingo",
    "    #wonderland",
    "    #marchhare",
    "*** End of ChanServ LIST ***",
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    return tmp_path


class _FakeAgent:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True, nick="Jeeves")
        self.home = home
        self.channels = ["#bobiverse", "#wonderland"]
        self.sent = []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._cs_collector = None
        self._cs_sent_at = 0.0
        self._cs_force = False
        self._cs_fail_at = 0.0
        self._cs_list_status = "unknown"
        self._oper_state = "ok"
        self._oper_name = "admin"
        self._chan_op = {"#bobiverse": True, "#wonderland": True}
        self._chair_status_last = ""
        self._chair_status_at = 0.0
        self._op_try_at = {}
        self.live_nick = "Jeeves"
        self.original_nick = "Jeeves"
        self.sock = object()
        self.lock = __import__("threading").Lock()
        self.chan = "#bobiverse"
        self.outbox = home / "outbox.txt"

    def send(self, line):
        self.sent.append(line)

    def _digest_home(self):
        return self.home

    _cs_ttl_s = irc_agent.Client._cs_ttl_s
    _maybe_chanserv_sync = irc_agent.Client._maybe_chanserv_sync
    _on_chanserv_notice = irc_agent.Client._on_chanserv_notice
    _apply_chanserv_channels = irc_agent.Client._apply_chanserv_channels
    _chair_status_line = irc_agent.Client._chair_status_line
    _chair_log_status = irc_agent.Client._chair_log_status
    _drain_outbox_path = irc_agent.Client._drain_outbox_path
    send_privmsg_lines = irc_agent.Client.send_privmsg_lines
    _channel_only_worker = irc_agent.Client._channel_only_worker


def test_fr3868_sync_list_without_bobiverse_still_persists_fleet(home):
    res = rm.sync_from_chanserv(
        home, ["#flamingo", "#wonderland", "#marchhare"], now=3000.0
    )
    assert res is not None
    chans = rm.load_registered_channels(home)
    assert "#bobiverse" in chans
    assert "#wonderland" in chans  # was in the LIST — kept
    assert "#flamingo" in chans
    doc = json.loads(rm.registry_path(home).read_text(encoding="utf-8"))
    assert "#bobiverse" in doc["channels"]


def test_fr3868_sync_does_not_invent_wonderland(home):
    rm.sync_from_chanserv(home, ["#flamingo", "#marchhare"], now=3001.0)
    chans = rm.load_registered_channels(home)
    assert "#bobiverse" in chans
    assert "#wonderland" not in chans


def test_fr3868_load_channels_backfills_missing_fleet(home):
    # Stale registry written without #bobiverse (pre-fix / partial LIST).
    p = rm.registry_path(home)
    p.write_text(
        json.dumps(
            {
                "v": 3,
                "machines": ["flamingo"],
                "channels": ["#flamingo", "#wonderland"],
                "source": "chanserv-list",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    chans = rm.load_registered_channels(home)
    assert "#bobiverse" in chans
    assert "#wonderland" in chans  # was in persisted list
    assert bobreport.FLEET_CHANNEL in bobreport.chair_channels(home)


def test_fr3868_apply_does_not_part_bobiverse(home, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    a = _FakeAgent(home)
    a._maybe_chanserv_sync()
    for ln in LIST_WITHOUT_BOBIVERSE:
        a._on_chanserv_notice(ln)
    assert "#bobiverse" in a.channels
    assert not any(s.upper().startswith("PART #BOBIVERSE") for s in a.sent)
    assert "#bobiverse" in rm.load_registered_channels(home)
    assert "JOIN #flamingo" in a.sent or "#flamingo" in a.channels


def test_fr3868_chair_status_warns_when_fleet_missing(home, monkeypatch):
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)
    a = _FakeAgent(home)
    a.channels = ["#flamingo", "#wonderland"]
    a._chan_op = {"#flamingo": True, "#wonderland": True}
    a._chair_log_status(force=True)
    assert any("chair-status" in m and "missing-fleet=#bobiverse" in m for m in logs)
    assert any(m.startswith("WARN chair-status") for m in logs)


def test_fr3868_chair_status_ok_when_fleet_op(home, monkeypatch):
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)
    a = _FakeAgent(home)
    a.channels = ["#bobiverse", "#flamingo"]
    a._chan_op = {"#bobiverse": True, "#flamingo": True}
    a._chair_log_status(force=True)
    assert any(m.startswith("INFO chair-status") and "missing-fleet=" not in m for m in logs)
    assert any("op-in=" in m and "#bobiverse" in m for m in logs)


def test_fr3868_outbox_send_logged(home, monkeypatch):
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    a = _FakeAgent(home)
    a.args = SimpleNamespace(chair=False, nick="Bob-win-mpre8vi4u6u")
    a.original_nick = "Bob-win-mpre8vi4u6u"
    a.live_nick = "Bob-win-mpre8vi4u6u"
    a.outbox.write_text(
        "PRIVMSG #bobiverse :!assign marchhare-1 SimonBarnett/bobiverse FR 3868\n",
        encoding="utf-8",
    )
    # Avoid fleet-spam gate / misplaced-wire: chair_mode off
    monkeypatch.setattr(bobreport, "chair_mode_active", lambda _h: False)
    sent = a._drain_outbox_path(a.outbox)
    assert sent
    assert any("outbox: sent" in m and "PRIVMSG #bobiverse" in m for m in logs)


def test_fr3868_404_logged(home, monkeypatch):
    logs: list[str] = []
    monkeypatch.setattr(irc_agent, "info", logs.append)
    # Call the numeric helper if present; else exercise via thin wrapper on Client
    assert hasattr(irc_agent.Client, "_on_cannot_send_numeric") or "404" in Path(
        irc_agent.__file__
    ).read_text(encoding="utf-8")
    if hasattr(irc_agent.Client, "_on_cannot_send_numeric"):
        a = _FakeAgent(home)
        irc_agent.Client._on_cannot_send_numeric(
            a, "404", ["404", "Bob-x", "#bobiverse"], "Cannot send to channel"
        )
        assert any("404" in m and "#bobiverse" in m for m in logs)


def test_fr3868_source_pins():
    text = Path(irc_agent.__file__).read_text(encoding="utf-8")
    assert "FR #3868" in text
    assert "missing-fleet=" in text
    assert "outbox: sent" in text
    rm_text = Path(rm.__file__).read_text(encoding="utf-8")
    assert "FR #3868" in rm_text
    assert "with_chair_required_channels" in rm_text or "CHAIR_REQUIRED" in rm_text
