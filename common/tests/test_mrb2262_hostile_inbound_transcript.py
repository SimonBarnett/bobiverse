"""Hostile MRB #2262: inbound transcript + ionos alias fold for Start-Bob channels."""
from __future__ import annotations

from pathlib import Path

import inbound_transcript as it

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "common/scripts/inbound_transcript.py"
IRC = ROOT / "common/scripts/irc_agent.py"


def test_mrb2262_ionos_channel_list_not_hash_ionos():
    assert it.channel_list_for_machine("ionos") == "#bobiverse,#win-mpre8vi4u6u"
    assert it.channel_list_for_machine("win-mpre8vi4u6u") == "#bobiverse,#win-mpre8vi4u6u"


def test_mrb2262_scrub_and_always_on_hook():
    assert "[redacted]" in it.scrub_text("password=sekrit ok")
    src = IRC.read_text(encoding="utf-8")
    assert "inbound_transcript" in src
    assert "append_inbound" in src
    assert not MOD.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mrb2262_fleet_canonical_ids():
    assert "win-mpre8vi4u6u" in it.FLEET_EAR_MACHINES
    assert "marchhare" in it.FLEET_EAR_MACHINES
    assert "flamingo" in it.FLEET_EAR_MACHINES
