"""FR #6245: frozen ear must not AttributeError when InstallRoot gitclaim lags FR #5203.

Crash a5c0ad2b69b9e02c on marchhare: FR #6237 prefers InstallRoot\\scripts over
_MEIPASS, so a new frozen irc_agent calling gitclaim.shop_line_resets_bored_clock
against a pre-FR #5203 disk gitclaim killed the reader thread.
"""
from __future__ import annotations

import types
from pathlib import Path

import irc_agent
from repo_layout import ROOT

AGENT = ROOT / "common" / "scripts" / "irc_agent.py"


def test_safe_shop_line_resets_bored_clock_uses_gitclaim_when_present():
    assert irc_agent.safe_shop_line_resets_bored_clock(
        "DONE FR SimonBarnett/bobiverse#1 https://x"
    )
    assert irc_agent.safe_shop_line_resets_bored_clock("ACK MRB SimonBarnett/hrsmith#2")
    assert not irc_agent.safe_shop_line_resets_bored_clock("!bored")
    assert not irc_agent.safe_shop_line_resets_bored_clock("hello")


def test_safe_shop_line_resets_bored_clock_fallback_when_attr_missing(monkeypatch):
    """Simulate FR #6237 loading a pre-FR #5203 InstallRoot gitclaim.py."""
    stale = types.SimpleNamespace(
        is_bored_command=lambda body: False,
        # deliberately no shop_line_resets_bored_clock
    )
    monkeypatch.setattr(irc_agent, "gitclaim", stale)
    assert irc_agent.safe_shop_line_resets_bored_clock(
        "DONE FR SimonBarnett/bobiverse#6245 https://x"
    )
    assert irc_agent.safe_shop_line_resets_bored_clock("NACK FR x/y#1 reason")
    assert irc_agent.safe_shop_line_resets_bored_clock("GIVEUP FR x/y#1 hung")
    assert not irc_agent.safe_shop_line_resets_bored_clock("!bored")
    assert not irc_agent.safe_shop_line_resets_bored_clock("")


def test_safe_shop_line_resets_bored_clock_fallback_when_attr_raises(monkeypatch):
    def boom(_body: str) -> bool:
        raise AttributeError("module 'gitclaim' has no attribute 'shop_line_resets_bored_clock'")

    monkeypatch.setattr(
        irc_agent.gitclaim,
        "shop_line_resets_bored_clock",
        boom,
        raising=False,
    )
    assert irc_agent.safe_shop_line_resets_bored_clock("ACK FR x/y#1")


def test_fr6245_maybe_git_claim_uses_safe_helper():
    text = AGENT.read_text(encoding="utf-8")
    claim = text[text.find("def _maybe_git_claim") : text.find("def _git_bored")]
    assert "safe_shop_line_resets_bored_clock" in claim
    assert "gitclaim.shop_line_resets_bored_clock(" not in claim


def test_fr6245_safe_helper_defined_before_maybe_git_claim():
    text = AGENT.read_text(encoding="utf-8")
    i_helper = text.find("def safe_shop_line_resets_bored_clock")
    i_claim = text.find("def _maybe_git_claim")
    assert i_helper != -1
    assert i_claim != -1
    assert i_helper < i_claim
