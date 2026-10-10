"""Hostile pins for MRB #3895 / FR #3893: offer next job after DONE (parity with GIVEUP #2811)."""
from __future__ import annotations

from pathlib import Path

import gitclaim
from repo_layout import ROOT

GITCLAIM = ROOT / "common" / "scripts" / "gitclaim.py"
IRC = ROOT / "common" / "scripts" / "irc_agent.py"
CMD_SKILL = (
    ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md"
)
MON_SKILL = (
    ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-monitor" / "SKILL.md"
)


def test_mrb3895_hostile_release_via_includes_done():
    assert "done" in gitclaim._RELEASE_OFFER_VIA
    assert "giveup" in gitclaim._RELEASE_OFFER_VIA
    assert "nack" in gitclaim._RELEASE_OFFER_VIA
    sticky = gitclaim.offer_timeout_s({"offered_via": "done"})
    assert sticky > gitclaim.OFFER_TIMEOUT_S
    assert sticky == gitclaim.OFFER_TIMEOUT_S + gitclaim.GIVEUP_OFFER_EXTRA_S


def test_mrb3895_hostile_contiguous_irc_agent_done_branch():
    irc = IRC.read_text(encoding="utf-8")
    done_at = irc.find('verb == "DONE" and status in ("ok", "missing")')
    assert done_at > 0
    window = irc[done_at : done_at + 2200]
    assert "offer_after_done" in window
    assert "done-offer" in window
    assert "done-offer empty" in window
    assert "WARN done-offer" in window
    # Must not wait only on !bored for the next hand-out after DONE.
    assert "do not wait for the seat's next !bored" in window or "FR #3893" in window


def test_mrb3895_hostile_gitclaim_offer_after_done_api():
    text = GITCLAIM.read_text(encoding="utf-8")
    assert "def offer_after_done(" in text
    assert "def offer_after_release(" in text
    assert '_RELEASE_OFFER_VIA = frozenset({"giveup", "done", "nack"})' in text
    assert 'offered_via="done"' in text
    # Alias retained for FR #2811 callers.
    assert "def offer_after_giveup(" in text


def test_mrb3895_hostile_skills_document_done_offer():
    cmd = CMD_SKILL.read_text(encoding="utf-8")
    mon = MON_SKILL.read_text(encoding="utf-8")
    assert "FR #2811 / #3893" in cmd or "FR #3893" in cmd
    assert "offer_after_done" in mon or "offered_via=done" in mon or "after DONE" in mon
    assert "done-offer" in cmd or "offer_after_done" in mon
    for p in (CMD_SKILL, MON_SKILL):
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM on {p.name}"
        assert raw.endswith(b"\n"), f"missing trailing newline on {p.name}"
