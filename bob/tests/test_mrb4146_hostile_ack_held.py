"""Hostile pins for MRB #4146 / FR #4115 (ACK on receipt, one held assign, missing-ACK hold)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WORKER = ROOT / "bob/scripts/bob_worker.py"
SKILL = ROOT / "bob/.grok/skills/bobiverse-bob-worker/SKILL.md"
GITCLAIM = ROOT / "common/scripts/gitclaim.py"
IRC = ROOT / "common/scripts/irc_agent.py"
SHOP = ROOT / "common/scripts/shop_listen.py"


def test_mrb4146_ack_helpers_and_release_first_only():
    import bob_worker as bw

    assign_a = (
        "FROM Jeeves #m m-1: FR SimonBarnett/bobiverse#10 "
        "https://github.com/SimonBarnett/bobiverse/issues/10"
    )
    assign_b = (
        "FROM Jeeves #m m-1: MRB SimonBarnett/bobiverse#20 "
        "https://github.com/SimonBarnett/bobiverse/pull/20"
    )
    assert bw.ack_on_receipt_line(assign_a) == "ACK FR SimonBarnett/bobiverse#10"
    assert bw.busy_holding_nack_line(assign_b, "FR SimonBarnett/bobiverse#10") == (
        "NACK MRB SimonBarnett/bobiverse#20 busy, holding FR SimonBarnett/bobiverse#10"
    )
    outbox: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True
    assert (
        relay.deliver(
            "Jeeves",
            "#m",
            "m-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
        )
        == "held_until_turn_end"
    )
    assert (
        relay.deliver(
            "Jeeves",
            "#m",
            "m-1: MRB SimonBarnett/bobiverse#20 https://github.com/SimonBarnett/bobiverse/pull/20",
        )
        == "held_until_turn_end"
    )
    relay.hold_assigns_while = lambda: False
    assert relay.release_held_assigns() == 1
    assert len(injected) == 1
    assert "bobiverse#10" in injected[0].lower()
    assert "ACK FR SimonBarnett/bobiverse#10" in outbox
    assert any("busy, holding FR SimonBarnett/bobiverse#10" in x for x in outbox)


def test_mrb4146_ack_before_inject_order():
    import bob_worker as bw

    order: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0)
    relay.write_outbox = lambda text: order.append("ack:" + text) or True
    relay.set_target(lambda line: order.append("inject") or True)
    st = relay.deliver(
        "Jeeves",
        "#m",
        "m-1: FR SimonBarnett/bobiverse#99 https://github.com/SimonBarnett/bobiverse/issues/99",
    )
    assert st == "injected"
    assert order[0].startswith("ack:ACK FR")
    assert order[1] == "inject"


def test_mrb4146_source_pins_note_seat_hold_missing_ack():
    gc = GITCLAIM.read_text(encoding="utf-8")
    assert "def note_seat_hold(" in gc
    assert "FR #4115" in gc or "ACK status=missing" in gc
    irc = IRC.read_text(encoding="utf-8")
    assert "note_seat_hold(" in irc
    assert 'status == "missing"' in irc or "status == 'missing'" in irc
    shop = SHOP.read_text(encoding="utf-8")
    assert "note_seat_hold(" in shop
    assert "FR #4115" in shop


def test_mrb4146_skill_ack_on_receipt_contiguous():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    assert "ACK on receipt" in text
    assert "busy, holding" in text
    assert "note_seat_hold" in text or "ACK status=missing" in text
    # Contiguous FR #4115 remainder bullet still present.
    assert "**ACK on receipt / one held assign (FR #4115):**" in text


def test_mrb4146_worker_wires_write_outbox():
    src = WORKER.read_text(encoding="utf-8")
    assert "write_outbox" in src
    assert "ack_on_receipt_line" in src
    assert "busy_holding_nack_line" in src
    assert "release_held_assigns" in src
