"""FR #4115 remainder: ACK on receipt before inject; release_held_assigns injects only
the first held assign and NACKs the rest without an agent turn."""
from __future__ import annotations

import bob_worker as bw


ASSIGN_A = (
    "FROM Jeeves #marchhare marchhare-1: FR SimonBarnett/bobiverse#10 "
    "https://github.com/SimonBarnett/bobiverse/issues/10"
)
ASSIGN_B = (
    "FROM Jeeves #marchhare marchhare-1: MRB SimonBarnett/bobiverse#20 "
    "https://github.com/SimonBarnett/bobiverse/pull/20"
)
ASSIGN_C = (
    "FROM Jeeves #marchhare marchhare-1: UAT SimonBarnett/bobiverse#30 "
    "https://github.com/SimonBarnett/bobiverse/issues/30"
)


def test_ack_on_receipt_line_helper():
    assert bw.ack_on_receipt_line(ASSIGN_A) == "ACK FR SimonBarnett/bobiverse#10"
    assert bw.ack_on_receipt_line(ASSIGN_B) == "ACK MRB SimonBarnett/bobiverse#20"
    assert bw.ack_on_receipt_line("FROM Jeeves #x nick: nothing queued") is None
    assert bw.ack_on_receipt_line("hello") is None


def test_busy_holding_nack_line_helper():
    nack = bw.busy_holding_nack_line(ASSIGN_B, "FR SimonBarnett/bobiverse#10")
    assert nack == "NACK MRB SimonBarnett/bobiverse#20 busy, holding FR SimonBarnett/bobiverse#10"
    assert bw.busy_holding_nack_line("nothing", "FR x#1") is None


def test_deliver_acks_before_inject():
    outbox: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    relay = bw.Relay(log=logs.append, clock=lambda: 0.0)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)

    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
    )
    assert st == "injected"
    assert outbox == ["ACK FR SimonBarnett/bobiverse#10"]
    assert len(injected) == 1
    assert "bobiverse#10" in injected[0].lower()
    # ACK must be recorded before inject (list order proves write_outbox ran first).
    assert any("ack on receipt" in m.lower() for m in logs)


def test_deliver_acks_on_hold_before_turn_end():
    outbox: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True

    st = relay.deliver(
        "Jeeves",
        "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
    )
    assert st == "held_until_turn_end"
    assert injected == []
    assert outbox == ["ACK FR SimonBarnett/bobiverse#10"]


def test_second_held_assign_not_acked_on_receipt():
    outbox: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: True)
    relay.hold_assigns_while = lambda: True

    assert relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
    ) == "held_until_turn_end"
    assert relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: MRB SimonBarnett/bobiverse#20 https://github.com/SimonBarnett/bobiverse/pull/20",
    ) == "held_until_turn_end"
    assert outbox == ["ACK FR SimonBarnett/bobiverse#10"]


def test_release_held_assigns_injects_first_nacks_rest():
    outbox: list[str] = []
    injected: list[str] = []
    logs: list[str] = []
    relay = bw.Relay(log=logs.append, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True

    relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
    )
    relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: MRB SimonBarnett/bobiverse#20 https://github.com/SimonBarnett/bobiverse/pull/20",
    )
    relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: UAT SimonBarnett/bobiverse#30 https://github.com/SimonBarnett/bobiverse/issues/30",
    )
    assert injected == []
    # Clear hold so release can inject.
    relay.hold_assigns_while = lambda: False
    n = relay.release_held_assigns()
    assert n == 1
    assert len(injected) == 1
    assert "bobiverse#10" in injected[0].lower()
    assert "ACK FR SimonBarnett/bobiverse#10" in outbox
    assert "NACK MRB SimonBarnett/bobiverse#20 busy, holding FR SimonBarnett/bobiverse#10" in outbox
    assert "NACK UAT SimonBarnett/bobiverse#30 busy, holding FR SimonBarnett/bobiverse#10" in outbox
    assert relay.has_pending_work() is False


def test_release_held_assigns_single_still_injects():
    outbox: list[str] = []
    injected: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0, max_pending=8)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: True
    relay.deliver(
        "Jeeves", "#marchhare",
        "marchhare-1: FR SimonBarnett/bobiverse#10 https://github.com/SimonBarnett/bobiverse/issues/10",
    )
    relay.hold_assigns_while = lambda: False
    assert relay.release_held_assigns() == 1
    assert len(injected) == 1
    assert outbox == ["ACK FR SimonBarnett/bobiverse#10"]


def test_nothing_queued_never_acks():
    outbox: list[str] = []
    relay = bw.Relay(log=lambda m: None, clock=lambda: 0.0)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda line: True)
    assert relay.deliver("Jeeves", "#marchhare", "marchhare-1: nothing queued") == "skipped"
    assert outbox == []
