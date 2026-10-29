"""FR #5204: publish a credential-free, synchronized list of connected consoles."""
from __future__ import annotations

from types import SimpleNamespace

import bobreport
import irc_agent


class FakeChair:
    def __init__(self, home):
        self.args = SimpleNamespace(chair=True)
        self.home = home
        self.channels = ["#bobiverse", "#wonderland", "#marchhare"]
        self.live_nick = "Jeeves"
        self._console_presence_synced = set()
        self._connected_console_nicks = None
        self._privs_engine = None

    def _digest_home(self):
        return self.home

    def _mine_nicks(self):
        return {"jeeves"}

    def send(self, line):
        pass

    def _workers(self):
        return SimpleNamespace(
            reconcile=lambda chan, present: None,
            on_leave=lambda nick, chan: None,
            on_quit=lambda nick: None,
            on_nick=lambda old, new: None,
        )

    _privs = irc_agent.Client._privs
    _privs_skip_whois = irc_agent.Client._privs_skip_whois
    _on_channel_names = irc_agent.Client._on_channel_names
    _publish_connected_console_nicks = irc_agent.Client._publish_connected_console_nicks
    _chair_wire = irc_agent.Client._chair_wire


def wire(chair, line):
    prefix, _, rest = line[1:].partition(" ")
    parts = rest.split(" ")
    trailing = rest.split(" :", 1)[1] if " :" in rest else ""
    chair._chair_wire(parts[0], parts, trailing, prefix, {})


def test_fr5204_publishes_only_after_all_channel_names_sync(tmp_path):
    chair = FakeChair(tmp_path)

    wire(chair, ":srv 353 Jeeves = #marchhare :marchhare_console bob-marchhare")
    wire(chair, ":srv 366 Jeeves #marchhare :End")
    report = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert report["connected_console_nicks"] == []
    assert report["connected_console_nicks_ready"] is False
    assert report["connected_console_nicks_updated_at"] == ""

    wire(chair, ":srv 353 Jeeves = #wonderland :lobby_console")
    wire(chair, ":srv 366 Jeeves #wonderland :End")
    wire(chair, ":srv 353 Jeeves = #bobiverse :random_console")
    wire(chair, ":srv 366 Jeeves #bobiverse :End")

    report = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert report["connected_console_nicks"] == [
        "lobby_console",
        "marchhare_console",
        "random_console",
    ]
    assert report["connected_console_nicks_ready"] is True
    assert report["connected_console_nicks_updated_at"].endswith("Z")


def test_fr5204_membership_changes_refresh_public_snapshot(tmp_path):
    chair = FakeChair(tmp_path)
    for channel, names in (
        ("#bobiverse", "random_console"),
        ("#wonderland", "lobby_console"),
        ("#marchhare", "marchhare_console"),
    ):
        wire(chair, f":srv 353 Jeeves = {channel} :{names}")
        wire(chair, f":srv 366 Jeeves {channel} :End")

    wire(chair, ":new_console!u@host JOIN #marchhare")
    assert "new_console" in bobreport.build_digest_object(tmp_path, "J")[
        "connected_console_nicks"
    ]

    wire(chair, ":new_console!u@host PART #marchhare :gone")
    assert "new_console" not in bobreport.build_digest_object(tmp_path, "J")[
        "connected_console_nicks"
    ]


def test_fr5204_digest_coerces_and_sorts_public_console_nicks(tmp_path):
    bobreport.set_connected_console_nicks(
        tmp_path, ["Zebra_console", "marchhare_console", "not-a-console", "marchhare_console"]
    )
    report = bobreport.build_digest_object(tmp_path, "J")
    assert report["connected_console_nicks"] == [
        "marchhare_console",
        "zebra_console",
    ]
