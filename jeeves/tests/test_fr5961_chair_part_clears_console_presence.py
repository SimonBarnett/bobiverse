"""FR #5961: chair PART/KICK clears airc_console_presence for that channel."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import bobreport
import irc_agent
import registered_machines as rm

from test_chair_worker_events import FakeChair, wire
from test_chanserv_roster_mirror import _FakeAgent


def _seed(tmp_path, mid="flamingo"):
    rm.save_registered(tmp_path, {mid})
    digest = bobreport.empty_digest()
    digest["machines"][mid] = bobreport._empty_machine(mid)
    digest["machines"][mid]["online"] = True
    digest["machines"][mid]["console_nicks"] = ["flamingo_console"]
    bobreport.save_digest(tmp_path, digest)
    bobreport.set_channel_console_presence(
        tmp_path, "#cust", ["cust_console"], machine="cust"
    )
    bobreport.set_channel_console_presence(
        tmp_path, "#other", ["other_console"], machine="other"
    )
    bobreport.set_channel_console_presence(
        tmp_path, "#bobiverse", ["fleet_console"], machine="fleet"
    )
    return mid


def _obj(home):
    return bobreport.build_digest_object(home, "Jeeves")


def _presence_channels(obj):
    return {
        str(r.get("channel") or "").lower()
        for r in (obj.get("airc_console_details") or [])
    }


def test_chanserv_part_clears_customer_presence_keeps_shop(tmp_path, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    mid = _seed(tmp_path)
    a = _FakeAgent(tmp_path)
    a.channels = ["#bobiverse", "#flamingo", "#cust", "#other"]
    # LIST keeps shop + #other + fleet; omits #cust -> PART #cust
    a._apply_chanserv_channels(["#bobiverse", "#flamingo", "#other"])
    assert any(s.startswith("PART #cust") for s in a.sent)
    assert "#cust" not in [c.lower() for c in a.channels]
    assert "#bobiverse" in [c.lower() for c in a.channels]
    obj = _obj(tmp_path)
    chans = _presence_channels(obj)
    assert "#cust" not in chans
    assert "cust_console" not in obj["airc_consoles"]
    assert "#other" in chans
    assert "other_console" in obj["airc_consoles"]
    assert obj["machines"][mid]["console_nicks"] == ["flamingo_console"]
    assert "flamingo_console" in obj["airc_consoles"]


def test_own_mixed_case_part_clears_presence(tmp_path, monkeypatch):
    mid = _seed(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    c = FakeChair(tmp_path)
    c.channels = ["#bobiverse", "#flamingo", "#Cust"]
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    wire(c, ":jeeves!u@h PART #Cust :bye")
    obj = _obj(tmp_path)
    assert "#cust" not in _presence_channels(obj)
    assert "cust_console" not in obj["airc_consoles"]
    assert "#other" in _presence_channels(obj)
    assert obj["machines"][mid]["console_nicks"] == ["flamingo_console"]


def test_kick_of_chair_clears_presence_shop_unchanged(tmp_path, monkeypatch):
    mid = _seed(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    c = FakeChair(tmp_path)
    c.channels = ["#bobiverse", "#flamingo", "#cust"]
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    wire(c, ":Op!u@h KICK #cust Jeeves :x")
    obj = _obj(tmp_path)
    assert "#cust" not in _presence_channels(obj)
    assert "cust_console" not in obj["airc_consoles"]
    assert obj["machines"][mid]["console_nicks"] == ["flamingo_console"]
    assert "#other" in _presence_channels(obj)


def test_kick_by_chair_of_console_does_not_wipe_channel(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    c = FakeChair(tmp_path)
    c.channels = ["#bobiverse", "#flamingo", "#cust"]
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    # Seed a second console on #cust so remove-one leaves the channel record.
    bobreport.set_channel_console_presence(
        tmp_path, "#cust", ["cust_console", "someone_console"], machine="cust"
    )
    wire(c, ":Jeeves!u@h KICK #cust someone_console :x")
    obj = _obj(tmp_path)
    assert "#cust" in _presence_channels(obj)
    assert "cust_console" in obj["airc_consoles"]
    assert "someone_console" not in obj["airc_consoles"]


def test_non_chair_part_does_not_wipe_channel(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    c = FakeChair(tmp_path)
    c.channels = ["#bobiverse", "#flamingo", "#cust"]
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    bobreport.set_channel_console_presence(
        tmp_path, "#cust", ["cust_console", "peer_console"], machine="cust"
    )
    wire(c, ":peer_console!u@h PART #cust :bye")
    obj = _obj(tmp_path)
    assert "#cust" in _presence_channels(obj)
    assert "cust_console" in obj["airc_consoles"]
    assert "peer_console" not in obj["airc_consoles"]


def test_own_shop_part_does_not_touch_console_nicks(tmp_path, monkeypatch):
    mid = _seed(tmp_path)
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    c = FakeChair(tmp_path)
    c.channels = ["#bobiverse", "#flamingo"]
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    before = list(_obj(tmp_path)["machines"][mid]["console_nicks"])
    wire(c, ":Jeeves!u@h PART #flamingo :bye")
    after = list(_obj(tmp_path)["machines"][mid]["console_nicks"])
    assert after == before == ["flamingo_console"]


def test_late_names_after_chanserv_part_does_not_restore_presence(tmp_path, monkeypatch):
    """MRB #5973: pending NAMES after ChanServ PART must not revive presence."""
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    _seed(tmp_path)
    a = _FakeAgent(tmp_path)
    a.channels = ["#bobiverse", "#flamingo", "#cust", "#other"]
    a._apply_chanserv_channels(["#bobiverse", "#flamingo", "#other"])
    assert "#cust" not in [c.lower() for c in a.channels]
    assert "#cust" not in _presence_channels(_obj(tmp_path))
    # Late NAMES for the removed channel (as if 353/366 still in flight).
    a._on_channel_names("#cust", {"cust_console", "someone"})
    obj = _obj(tmp_path)
    assert "#cust" not in _presence_channels(obj)
    assert "cust_console" not in obj["airc_consoles"]
    assert "#other" in _presence_channels(obj)
