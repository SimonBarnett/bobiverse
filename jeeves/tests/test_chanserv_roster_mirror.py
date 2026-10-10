import json
import time
from types import SimpleNamespace

import pytest

import bobreport
import irc_agent
import registered_machines as rm

LIST_OK = [
    "*** ChanServ LIST ***",
    "    #bobiverse",
    "    #flamingo",
    "    #win-mpre8vi4u6u",
    "    #CE-Priority-Dev1",
    "    #agentic_irc",
    "    ##weird",
    "*** End of ChanServ LIST ***",
]


def _collect(lines):
    c = rm.ChanServListCollector()
    for ln in lines:
        c.feed(ln)
    return c


def test_collector_parses_ergo_list_notices():
    c = _collect(LIST_OK)
    assert c.done and not c.failed
    assert rm.machine_ids_from_channels(c.channels) == {"flamingo", "win-mpre8vi4u6u", "ce-priority-dev1"}


def test_machine_filter_excludes_bobiverse_and_non_machine(monkeypatch):
    assert rm.machine_ids_from_channels(["#bobiverse", "#BobIverse", "#a_b", "##x", "nochan", "#ok-1"]) == {"ok-1"}
    # FR #3834: #wonderland is never a machine shop.
    assert rm.machine_ids_from_channels(["#wonderland", "#Wonderland", "#flamingo"]) == {"flamingo"}
    monkeypatch.setenv(rm.EXCLUDE_ENV, "#general, lobby")
    assert rm.machine_ids_from_channels(["#general", "#lobby", "#flamingo"]) == {"flamingo"}


def test_collector_incomplete_or_denied_is_not_done():
    c = _collect(LIST_OK[:4])
    assert not c.done                      # no End marker -> never applied
    d = _collect(["Insufficient privileges"])
    assert d.failed and not d.done
    # stray notices before the start marker are ignored, not a failure
    e = _collect(["Welcome to ChanServ", *LIST_OK])
    assert e.done and not e.failed


def test_sync_adds_and_removes_mirror(tmp_path):
    rm.save_registered(tmp_path, {"flamingo", "old-box"})
    added, removed = rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#flamingo", "#new-box"], now=1000.0)
    assert added == {"new-box"} and removed == {"old-box"}
    assert rm.load_registered(tmp_path) == {"flamingo", "new-box"}
    doc = json.loads(rm.registry_path(tmp_path).read_text(encoding="utf-8"))
    assert doc["source"] == "chanserv-list" and doc["refreshed_ts"] == 1000.0
    # channel unregistered on ChanServ later -> gone from cache AND digest roster/channels
    rm.sync_from_chanserv(tmp_path, ["#bobiverse", "#new-box"], now=1100.0)
    assert rm.load_registered(tmp_path) == {"new-box"}
    out = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert out["roster_machine_ids"] == ["new-box"]
    assert out["chair_channels"] == ["#bobiverse", "#wonderland", "#new-box"]
    assert set(out["machines"]) == {"new-box"}


def test_outage_or_empty_result_keeps_last_good_list(tmp_path):
    rm.sync_from_chanserv(tmp_path, ["#flamingo", "#marchhare"], now=1000.0)
    assert rm.sync_from_chanserv(tmp_path, []) is None
    assert rm.sync_from_chanserv(tmp_path, ["#bobiverse"]) is None   # only non-machine channels
    assert rm.load_registered(tmp_path) == {"flamingo", "marchhare"}
    assert rm.registry_meta(tmp_path)["refreshed_ts"] == 1000.0       # not bumped by a failed sync


def test_ttl_due(tmp_path):
    assert rm.refresh_due(tmp_path, 120, now=5000.0)                  # never synced
    rm.sync_from_chanserv(tmp_path, ["#flamingo"], now=5000.0)
    assert not rm.refresh_due(tmp_path, 120, now=5100.0)
    assert rm.refresh_due(tmp_path, 120, now=5121.0)
    rm.add_registered(tmp_path, "marchhare")                           # !register must not fake freshness
    assert rm.registry_age_s(tmp_path, now=5100.0) == 100.0


def test_no_hardcoded_fleet_fallback(tmp_path):
    assert not hasattr(bobreport, "FLEET_MACHINE_IDS")
    assert bobreport.roster_machine_ids(tmp_path) == ()
    assert "ionos" not in bobreport.roster_machine_ids(tmp_path)
    assert bobreport.chair_channels(tmp_path) == ["#bobiverse", "#wonderland"]
    assert bobreport.empty_digest()["machines"] == {}
    assert bobreport.build_digest_object(tmp_path, "Jeeves")["roster_machine_ids"] == []


def test_legacy_registry_file_without_meta_still_loads(tmp_path):
    (tmp_path / "registered-machines.json").write_text('{"v":1,"machines":["flamingo","Bad Id"]}', encoding="utf-8")
    assert rm.load_registered(tmp_path) == {"flamingo"}
    assert rm.registry_age_s(tmp_path) is None


class _FakeAgent:
    """Just enough of IrcAgent to drive the sync state machine."""

    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.channels = ["#bobiverse"]
        self.sent = []
        self.joined = SimpleNamespace(is_set=lambda: True)
        self._cs_collector = None
        self._cs_sent_at = 0.0
        self._cs_force = False
        self._cs_fail_at = 0.0
        self._cs_list_status = "unknown"
        self._oper_state = "ok"
        self._oper_name = "admin"

    def send(self, line):
        self.sent.append(line)

    def _digest_home(self):
        return self.home

    _cs_ttl_s = irc_agent.Client._cs_ttl_s
    _maybe_chanserv_sync = irc_agent.Client._maybe_chanserv_sync
    _on_chanserv_notice = irc_agent.Client._on_chanserv_notice
    _apply_chanserv_channels = irc_agent.Client._apply_chanserv_channels


def test_chair_sends_list_then_mirrors_and_joins_parts(tmp_path):
    rm.save_registered(tmp_path, {"gone-box"})
    a = _FakeAgent(tmp_path)
    a.channels += ["#gone-box"]
    a._maybe_chanserv_sync()
    assert a.sent == ["PRIVMSG ChanServ :LIST"]
    a._maybe_chanserv_sync()                        # in flight: no second LIST
    assert len(a.sent) == 1
    for ln in LIST_OK:
        a._on_chanserv_notice(ln)
    assert rm.load_registered(tmp_path) == {"flamingo", "win-mpre8vi4u6u", "ce-priority-dev1"}
    assert "JOIN #flamingo" in a.sent and "JOIN #win-mpre8vi4u6u" in a.sent
    assert any(s.startswith("PART #gone-box") for s in a.sent)
    assert "#gone-box" not in a.channels
    n = len(a.sent)
    a._maybe_chanserv_sync()                        # fresh -> within TTL, no LIST
    assert len(a.sent) == n


def test_chair_denied_keeps_roster_and_backs_off(tmp_path):
    rm.sync_from_chanserv(tmp_path, ["#flamingo"], now=time.time() - 10_000)
    a = _FakeAgent(tmp_path)
    a._maybe_chanserv_sync()
    a._on_chanserv_notice("Command restricted")
    assert rm.load_registered(tmp_path) == {"flamingo"}
    a._maybe_chanserv_sync()
    assert a.sent == ["PRIVMSG ChanServ :LIST"]     # backoff: not re-sent immediately


def test_register_command_forces_resync(tmp_path):
    a = _FakeAgent(tmp_path)
    rm.sync_from_chanserv(tmp_path, ["#flamingo"], now=time.time())   # fresh
    a._maybe_chanserv_sync()
    assert a.sent == []
    a._cs_force = True                                  # what !register sets
    a._maybe_chanserv_sync()
    assert a.sent == ["PRIVMSG ChanServ :LIST"]


def test_register_handler_adds_and_flags_refresh():
    src = (__import__("pathlib").Path(irc_agent.__file__)).read_text(encoding="utf-8")
    h = src.split("def _handle_register_command", 1)[1].split("def _maybe_grant_bob_modes", 1)[0]
    assert "add_registered(self._digest_home()" in h and "self._cs_force = True" in h


def test_stale_timeout_keeps_roster(tmp_path, monkeypatch):
    rm.sync_from_chanserv(tmp_path, ["#flamingo"], now=time.time() - 10_000)
    a = _FakeAgent(tmp_path)
    a._maybe_chanserv_sync()
    a._cs_sent_at -= 60                              # reply never arrived
    a._maybe_chanserv_sync()
    assert a._cs_collector is None and rm.load_registered(tmp_path) == {"flamingo"}

