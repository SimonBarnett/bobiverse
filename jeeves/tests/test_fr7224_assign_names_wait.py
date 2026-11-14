"""FR #7224: !assign NAMES refresh applies 353/366 before refuse (no reader deadlock)."""
from __future__ import annotations

from types import SimpleNamespace

import gitclaim
import irc_agent
from test_fr7186_shop_membership import (
    OTHER,
    SEAT,
    FakeChair,
    _chair,
    _queue_fr,
    listed,
    wire,
)


class AssignChair(FakeChair):
    _maybe_assign = irc_agent.Client._maybe_assign
    _names_refresh_for_assign = irc_agent.Client._names_refresh_for_assign
    _assign_row_named = irc_agent.Client._assign_row_named
    _finish_assign_result = irc_agent.Client._finish_assign_result
    _resume_assign_after_names = irc_agent.Client._resume_assign_after_names
    _expire_pending_names_assign = irc_agent.Client._expire_pending_names_assign
    _on_channel_names = irc_agent.Client._on_channel_names
    _principal = irc_agent.Client._principal
    _cmd_reply = irc_agent.Client._cmd_reply
    _cmd_trace = irc_agent.Client._cmd_trace
    _whois_hint = irc_agent.Client._whois_hint
    _account_of = irc_agent.Client._account_of
    _ear_machine = lambda self, n: None  # noqa: E731

    def whisper(self, nick, text):
        self.pms.append((nick, text))


def _assign_chair(tmp_path, monkeypatch):
    monkeypatch.setattr(irc_agent, "FLOOD_S", 0)
    monkeypatch.setattr(
        gitclaim,
        "github_issue_open_checker",
        lambda **_k: (lambda *_a, **_kw: True),
    )
    monkeypatch.setattr(
        gitclaim,
        "github_pr_exists_checker",
        lambda **_k: (lambda *_a, **_kw: True),
    )
    monkeypatch.setattr(
        gitclaim,
        "github_is_pull_checker",
        lambda **_k: (lambda *_a, **_kw: False),
    )
    base = _chair(tmp_path, monkeypatch)
    c = AssignChair(tmp_path)
    c.home = base.home
    c.channels = base.channels
    c._chan_op = base._chan_op
    c.accounts = {"simon": "simon"}
    c.pms = []
    monkeypatch.setattr(irc_agent, "info", lambda m: c.logs.append(m))
    return c


def test_assign_row_wait_does_not_refuse(tmp_path, monkeypatch):
    chair = _chair(tmp_path, monkeypatch)
    _queue_fr(chair.home)
    wire(chair, f":{OTHER}!u@h JOIN #marchhare")
    sent = []

    def refresh(shop):
        sent.append(shop)
        return "wait"

    st, res = gitclaim.assign_row(
        chair.home,
        SEAT,
        "SimonBarnett/bobiverse",
        "FR",
        "#7179",
        issue_open=lambda *_: True,
        names_refresh=refresh,
    )
    assert st == "waiting"
    assert str(res).lower() == "#marchhare"
    assert sent == ["#marchhare"]
    assert SEAT not in listed(chair.home)


def test_single_assign_ok_after_names_366(tmp_path, monkeypatch):
    chair = _assign_chair(tmp_path, monkeypatch)
    _queue_fr(chair.home)
    wire(chair, f":{OTHER}!u@h JOIN #marchhare")
    assert OTHER in listed(chair.home)
    assert SEAT not in listed(chair.home)
    ok = chair._maybe_assign(
        "simon",
        "#marchhare",
        f"!assign {SEAT} SimonBarnett/bobiverse FR 7179",
        to_channel=True,
    )
    assert ok is True
    assert any(s.startswith("NAMES #marchhare") for s in chair.sent)
    assert not chair.said
    assert not any("refused" in t for _, t in chair.pms)
    wire(
        chair,
        f":srv 353 Jeeves = #marchhare :@Jeeves +bob-marchhare {SEAT} {OTHER}",
    )
    wire(chair, ":srv 366 Jeeves #marchhare :End of /NAMES list.")
    assert SEAT in listed(chair.home)
    assert chair.said, chair.pms
    assert any("assign: sent" in t for _, t in chair.pms)
    assert not any("refused" in t for _, t in chair.pms)
