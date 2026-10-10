"""Hostile pins for MRB #3873 / FR #3868 keep #bobiverse across ChanServ sync."""
from __future__ import annotations

from pathlib import Path

import registered_machines as rm
from repo_layout import ROOT

RM = ROOT / "common" / "scripts" / "registered_machines.py"
IRC = ROOT / "common" / "scripts" / "irc_agent.py"
SKILL = (
    ROOT
    / "jeeves"
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-troubleshooting"
    / "SKILL.md"
)


def test_mrb3873_hostile_required_channels_only_bobiverse():
    assert rm.CHAIR_REQUIRED_CHANNELS == ("#bobiverse",)
    assert "#wonderland" not in rm.CHAIR_REQUIRED_CHANNELS


def test_mrb3873_hostile_sync_omits_wonderland_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_DIGEST_HOME", str(tmp_path))
    rm.sync_from_chanserv(tmp_path, ["#flamingo", "#marchhare"], now=4000.0)
    chans = rm.load_registered_channels(tmp_path)
    assert "#bobiverse" in chans
    assert "#wonderland" not in chans
    assert "#flamingo" in chans


def test_mrb3873_hostile_contiguous_source_and_skill():
    text = RM.read_text(encoding="utf-8")
    assert 'CHAIR_REQUIRED_CHANNELS = ("#bobiverse",)' in text
    assert "never invent #wonderland" in text
    irc = IRC.read_text(encoding="utf-8")
    assert "never PART #bobiverse even if a LIST omitted it" in irc
    assert "INFO outbox: sent" in irc
    assert "ERR_CANNOTSENDTOCHAN" in irc
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3868" in skill
    assert "missing-fleet=#bobiverse" in skill
    assert not SKILL.read_bytes().startswith(b"\xef\xbb\xbf")
