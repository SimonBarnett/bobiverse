"""FR #3836: Jeeves joins every registered ChanServ channel; Bob ears get +o in #wonderland.

Never ops *_console or worker/seat nicks. channel-sync / op-grant INFO shapes.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import bobreport
import chan_privs as cp
import irc_agent
import registered_machines as rm

LIST_WITH_WONDERLAND = [
    "*** ChanServ LIST ***",
    "    #bobiverse",
    "    #flamingo",
    "    #wonderland",
    "    #agentic_irc",
    "*** End of ChanServ LIST ***",
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    return tmp_path


def test_wonderland_never_a_machine_id(home):
    res = rm.sync_from_chanserv(
        home, ["#bobiverse", "#wonderland", "#marchhare", "#Wonderland"], now=1000.0
    )
    assert res is not None
    assert rm.load_registered(home) == {"marchhare"}
    assert "wonderland" not in rm.load_registered(home)
    chans = rm.load_registered_channels(home)
    assert "#wonderland" in chans
    assert "#marchhare" in chans
    assert "#bobiverse" in chans
    assert bobreport.chair_channels(home) == chans


def test_sync_persists_full_channels_list(home):
    rm.sync_from_chanserv(
        home, ["#bobiverse", "#flamingo", "#wonderland"], now=2000.0
    )
    doc = json.loads(rm.registry_path(home).read_text(encoding="utf-8"))
    assert doc["v"] == 3
    assert set(doc["machines"]) == {"flamingo"}
    assert "#wonderland" in doc["channels"]
    assert "#flamingo" in doc["channels"]


def test_chair_channels_includes_wonderland_from_registry(home):
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare", "#wonderland"], now=1.0)
    assert "#wonderland" in bobreport.chair_channels(home)
    assert bobreport.roster_machine_ids(home) == ("marchhare",)


class _FakeAgent:
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


def test_chair_joins_all_registered_including_wonderland(home, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0.0)
    rm.save_registered(home, {"gone-box"})
    a = _FakeAgent(home)
    a.channels += ["#gone-box"]
    a._maybe_chanserv_sync()
    for ln in LIST_WITH_WONDERLAND:
        a._on_chanserv_notice(ln)
    assert rm.load_registered(home) == {"flamingo"}
    assert "JOIN #wonderland" in a.sent
    assert "JOIN #flamingo" in a.sent
    assert "JOIN #agentic_irc" in a.sent
    assert any(s.startswith("PART #gone-box") for s in a.sent)
    assert "#wonderland" in a.channels
    assert "#gone-box" not in a.channels
    assert registered_machines_channel_sync_shape(home)


def registered_machines_channel_sync_shape(home):
    chans = rm.load_registered_channels(home)
    return "#wonderland" in chans and len(chans) >= 3


def test_channel_sync_info_shape_in_apply_source():
    src = (__import__("pathlib").Path(irc_agent.__file__)).read_text(encoding="utf-8")
    assert "INFO channel-sync registered=" in src
    assert "joined=" in src
    assert "FLOOD_S" in src.split("def _apply_chanserv_channels", 1)[1].split(
        "def _handle_register_command", 1
    )[0]


class FakePriv:
    def __init__(self, home, *, channels=None):
        self.sent, self.logs, self.t = [], [], 1000.0
        chans = channels or ["#bobiverse", "#marchhare", "#wonderland"]
        self.ops = {c.lower(): True for c in chans}
        self.eng = cp.ChanPrivEngine(
            send=self.sent.append,
            log=self.logs.append,
            now=lambda: self.t,
            me=lambda: "Jeeves",
            channels=lambda: list(chans),
            is_registered=lambda mid: rm.is_registered(home, mid),
            normalize=bobreport.normalize_machine_id,
            chan_op=lambda ch: self.ops.get(ch.lower(), False),
            is_oper=lambda: False,
            accounts={"simon"},
        )

    def line(self, raw):
        tags, rest, prefix = {}, raw, ""
        if rest.startswith("@"):
            tag_part, _, rest = rest[1:].partition(" ")
            tags = dict(p.split("=", 1) for p in tag_part.split(";") if "=" in p)
        if rest.startswith(":"):
            prefix, _, rest = rest[1:].partition(" ")
        parts = rest.split(" ")
        trailing = rest.split(" :", 1)[1] if " :" in rest else ""
        self.eng.on_line(parts[0], parts, trailing, prefix, tags)

    def names(self, chan, members):
        self.line(f":srv 353 Jeeves = {chan} :{members}")
        self.line(f":srv 366 Jeeves {chan} :End of /NAMES list.")

    def modes(self):
        return [s for s in self.sent if s.startswith(("MODE", "SAMODE"))]


@pytest.fixture
def priv(home):
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare", "#wonderland"], now=1.0)
    return FakePriv(home)


def test_bob_ear_gets_plus_o_in_wonderland(priv):
    priv.names("#wonderland", "@Jeeves bob-marchhare")
    assert "MODE #wonderland +o bob-marchhare" in priv.modes()
    assert any(
        ln.startswith("INFO op-grant nick=bob-marchhare channel=#wonderland")
        for ln in priv.logs
    )


def test_bob_ear_reopped_on_resync_in_wonderland(priv):
    priv.names("#wonderland", "@Jeeves bob-marchhare")
    priv.sent.clear()
    priv.logs.clear()
    priv.t += 30.0
    # De-op reflected in NAMES, then reconcile apply
    priv.names("#wonderland", "@Jeeves bob-marchhare")
    assert "MODE #wonderland +o bob-marchhare" in priv.modes()


def test_console_and_worker_never_opped_in_wonderland(priv):
    priv.names(
        "#wonderland",
        "@Jeeves marchhare_console marchhare-960 flamingo-101 bob-evil",
    )
    assert priv.modes() == []


def test_bob_of_other_machine_still_opped_in_wonderland(home, priv):
    """Policy: every registered bob-* ear gets +o in #wonderland (not shop-scoped)."""
    rm.sync_from_chanserv(
        home, ["#bobiverse", "#marchhare", "#flamingo", "#wonderland"], now=2.0
    )
    priv.names("#wonderland", "@Jeeves bob-flamingo")
    assert "MODE #wonderland +o bob-flamingo" in priv.modes()


def test_docs_and_skill_mention_wonderland_setup():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    docs = (root / "docs" / "channel-privileges-and-workers.md").read_text(encoding="utf-8")
    assert "#wonderland" in docs
    assert "FLAGS" in docs or "AMODE" in docs or "ChanServ" in docs
    skill = (root / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "wonderland" in skill.lower()
    assert "channel-sync" in skill or "registered channel" in skill.lower()
