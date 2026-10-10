"""Bobiverse #3868: Jeeves always joins #bobiverse PLUS every registered channel.

Live Ergo's ChanServ LIST omits #bobiverse, so FR #3836 channel-sync PARTed it and ears'
outbox !assign / !resync / !bored in #bobiverse never reached Jeeves.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import bobreport
import irc_agent
import registered_machines as rm

LIVE_LIST = [  # ionos 2026-10-10: no #bobiverse in the LIST
    "#marchhare", "#win-mpre8vi4u6u", "#flamingo", "#walrus", "#ce-priority-dev1", "#wonderland",
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    return tmp_path


def _agent(home, channels):
    sent: list[str] = []
    return SimpleNamespace(
        args=SimpleNamespace(chair=True),
        home=home,
        channels=list(channels),
        sent=sent,
        send=sent.append,
        _digest_home=lambda: home,
    )


def test_chair_join_channels_static_plus_registered():
    out = rm.chair_join_channels(LIVE_LIST)
    assert out[0] == "#bobiverse"
    assert out[1:] == LIVE_LIST
    # no duplicates when LIST does include it (any case)
    dup = rm.chair_join_channels(["#flamingo", "#BobiVerse"])
    assert [c.lower() for c in dup].count("#bobiverse") == 1


def test_channel_sync_never_parts_bobiverse_when_list_omits_it(home, monkeypatch, capsys):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    a = _agent(home, ["#bobiverse", "#wonderland", "#gone-box"])
    irc_agent.Client._apply_chanserv_channels(a, LIVE_LIST)
    assert not any(s.lower().startswith("part #bobiverse") for s in a.sent), a.sent
    assert "#bobiverse" in [c.lower() for c in a.channels]
    assert any(s.startswith("PART #gone-box") for s in a.sent)
    assert "JOIN #flamingo" in a.sent
    out = capsys.readouterr()
    text = out.out + out.err
    if "channel-sync" in text:
        assert "registered=6 joined=#bobiverse," in text


def test_channel_sync_rejoins_bobiverse_if_missing(home, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    monkeypatch.setattr(irc_agent.time, "sleep", lambda s: None)
    a = _agent(home, ["#wonderland"])
    irc_agent.Client._apply_chanserv_channels(a, LIVE_LIST)
    assert "JOIN #bobiverse" in a.sent
    assert "#bobiverse" in a.channels


def test_chair_channels_at_startup_include_bobiverse(home):
    rm.sync_from_chanserv(home, LIVE_LIST, now=1.0)
    assert "#bobiverse" not in rm.load_registered_channels(home)  # mirror stays exact
    chans = bobreport.chair_channels(home)
    assert chans[0] == "#bobiverse"
    assert set(LIVE_LIST) <= set(chans)
