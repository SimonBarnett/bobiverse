from __future__ import annotations

from pathlib import Path

import bobreport
import irc_agent
import registered_machines as rm


def _client(home: Path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(home))
    rm.sync_from_chanserv(home, ["#bobiverse", "#marchhare"])
    bobreport._SEAT_ROSTER_CACHE["key"] = None
    monkeypatch.setattr(irc_agent, "info", lambda _line: None)

    client = irc_agent.Client.__new__(irc_agent.Client)
    client.args = type("Args", (), {"chair": True})()
    client.home = home
    client.live_nick = client.original_nick = "Jeeves"
    client.channels = ["#bobiverse", "#marchhare"]
    client._console_names_synced = set()
    client._privs_engine = None
    client._worker_tracker = None
    client._chan_op = {}
    client._oper_state = "off"
    client._op_try_at = {}
    client.send = lambda _line: None
    client._digest_home = lambda: home
    client._mine_nicks = lambda: {"jeeves"}
    return client


def _wire(client, command: str, parts: list[str], trailing: str = "", prefix: str = "") -> None:
    client._chair_wire(command, parts, trailing, prefix, {})


def test_console_presence_digest_is_normalized_and_public(tmp_path: Path):
    bobreport.update_connected_console_nicks(
        tmp_path, ["Walrus_console", "marchhare_console", "walrus_CONSOLE", "bob-worker", "bad nick"]
    )

    digest = bobreport.build_digest_object(tmp_path, "Jeeves")
    assert digest["connected_console_nicks"] == ["marchhare_console", "Walrus_console"]
    assert digest["console_presence_updated_at"].endswith("Z")


def test_chair_publishes_names_and_tracks_membership_changes(tmp_path: Path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _wire(
        client,
        "353",
        ["353", "Jeeves", "=", "#bobiverse"],
        "Jeeves Fleet_console",
    )
    _wire(client, "366", ["366", "Jeeves", "#bobiverse"])
    assert bobreport.build_digest_object(tmp_path, "Jeeves")["connected_console_nicks"] == []

    _wire(
        client,
        "353",
        ["353", "Jeeves", "=", "#marchhare"],
        "@Jeeves marchhare_console Walrus_console bob-marchhare",
    )
    _wire(client, "366", ["366", "Jeeves", "#marchhare"])

    assert bobreport.build_digest_object(tmp_path, "Jeeves")["connected_console_nicks"] == [
        "Fleet_console",
        "marchhare_console",
        "Walrus_console",
    ]

    _wire(client, "PART", ["PART", "#marchhare"], "leaving", "Walrus_console!u@h")
    assert bobreport.build_digest_object(tmp_path, "Jeeves")["connected_console_nicks"] == [
        "Fleet_console",
        "marchhare_console"
    ]

    _wire(client, "JOIN", ["JOIN", "#marchhare"], "", "new_console!u@h")
    assert bobreport.build_digest_object(tmp_path, "Jeeves")["connected_console_nicks"] == [
        "Fleet_console",
        "marchhare_console",
        "new_console",
    ]

    _wire(client, "NICK", ["NICK", "renamed_console"], "", "new_console!u@h")
    _wire(client, "QUIT", ["QUIT"], "gone", "marchhare_console!u@h")
    assert bobreport.build_digest_object(tmp_path, "Jeeves")["connected_console_nicks"] == [
        "Fleet_console",
        "renamed_console"
    ]
