"""FR #2333: empty bored reply is seat-relative (never N>0 offerable for you)."""
from __future__ import annotations

import gitclaim


def test_fr2333_clamp_empty_reply_zeros_offerable():
    stats = {
        "unaccepted": 38,
        "offerable": 1,
        "out_of_focus": 35,
        "require_machine": 2,
        "self_mrb": 0,
        "ledger": 0,
        "sticky_offered": 0,
    }
    clamped = gitclaim.clamp_empty_reply_stats(stats)
    assert clamped["offerable"] == 0
    assert clamped["blocked_other"] == 1
    line = gitclaim.format_nothing_queued("win-mpre8vi4u6u-14452", clamped)
    assert "0 offerable for you under focus" in line
    assert "blocked_other=1" in line
    assert "1 offerable" not in line.split("for you")[0]  # no positive claim before for you


def test_fr2333_format_says_for_you():
    line = gitclaim.format_nothing_queued(
        "marchhare-1",
        {
            "unaccepted": 10,
            "offerable": 0,
            "out_of_focus": 8,
            "require_machine": 1,
            "self_mrb": 1,
        },
    )
    assert "offerable for you under focus" in line
    assert "self_mrb=1" in line


def test_fr2333_irc_agent_clamps_on_empty_path():
    src = (gitclaim.__file__ and open(__import__("pathlib").Path(__file__).resolve().parents[2] / "common/scripts/irc_agent.py", encoding="utf-8").read())
    assert "clamp_empty_reply_stats" in src
    assert "summarize_empty_offer" in src
