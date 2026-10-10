"""FR #3835: Bob ears join #wonderland on every connect/reconnect; workers never."""

from __future__ import annotations

from pathlib import Path

import bobreport
import inbound_transcript as it

ROOT = Path(__file__).resolve().parents[2]
START_BOB = ROOT / "bob" / "scripts" / "Start-Bob.ps1"
IRC_AGENT = ROOT / "common" / "scripts" / "irc_agent.py"
BOB_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
EAR_DOC = ROOT / "bob" / "docs" / "bob-ear.md"


def test_wonderland_constant_fixed():
    assert bobreport.WONDERLAND_CHANNEL == "#wonderland"


def test_bob_ear_channels_include_wonderland_fleet_and_shop():
    chans = bobreport.channels_for_nick(
        "Bob-marchhare", "#bobiverse,#marchhare"
    )
    assert chans == ["#bobiverse", "#wonderland", "#marchhare"]
    # reconnect path reuses channels_for_nick - same list every session
    again = bobreport.channels_for_nick("Bob-ionos", "ignored")
    assert again[0] == "#bobiverse"
    assert again[1] == "#wonderland"
    assert again[2].startswith("#")
    assert "#wonderland" in again


def test_worker_and_talk_seat_never_join_wonderland():
    # Legacy w-* worker nick: shop only even if requested list includes wonderland
    mid = next(iter(bobreport.SHORT_ID))
    short = bobreport.SHORT_ID[mid]
    wnick = f"w-{short}-960"
    worker = bobreport.channels_for_nick(
        wnick, "#bobiverse,#wonderland,#" + mid
    )
    assert worker == [f"#{mid}"]
    assert "#wonderland" not in worker
    assert "#bobiverse" not in worker

    # Seat nick when machine is on the seat roster
    import unittest.mock as mock

    with mock.patch.object(bobreport, "seat_machine_ids", return_value=(mid,)):
        seat = bobreport.channels_for_nick(
            f"{mid}-960", "#bobiverse,#wonderland,#" + mid
        )
        assert seat == [f"#{mid}"]
        assert "#wonderland" not in seat
        assert bobreport.worker_channel_allowed(f"{mid}-1234", "#wonderland") is False
        assert bobreport.worker_channel_allowed(f"{mid}-1234", f"#{mid}") is True

    # bob_worker JOIN is shop-only (hardcoded)
    bw = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "JOIN " in bw and "self.shop" in bw
    assert "#wonderland" not in bw

    assert bobreport.worker_channel_allowed(wnick, "#wonderland") is False
    assert bobreport.worker_channel_allowed(wnick, f"#{mid}") is True
    assert bobreport.worker_channel_allowed("Bob-marchhare", "#wonderland") is True


def test_channel_list_for_machine_matches_start_bob():
    assert it.channel_list_for_machine("marchhare") == "#bobiverse,#wonderland,#marchhare"
    assert it.channel_list_for_machine("ionos") == "#bobiverse,#wonderland,#win-mpre8vi4u6u"
    text = START_BOB.read_text(encoding="utf-8")
    assert "#wonderland" in text
    assert 'channel = "#bobiverse,#wonderland,$shop"' in text or (
        "#bobiverse,#wonderland,$shop" in text
    )


def test_irc_agent_logs_wonderland_join_reason():
    src = IRC_AGENT.read_text(encoding="utf-8")
    assert "reason=bob-ear-fleet-channel" in src
    assert "WONDERLAND_CHANNEL" in src or "#wonderland" in src
    # session() joins self.channels each connect (reconnect covered)
    assert "for ch in self.channels:" in src
    assert "JOIN " in src


def test_docs_and_skill_list_wonderland():
    skill = BOB_SKILL.read_text(encoding="utf-8")
    assert "#wonderland" in skill
    ear = EAR_DOC.read_text(encoding="utf-8")
    assert "#wonderland" in ear
    assert "bob-ear-fleet-channel" in ear or "FR #3835" in ear
