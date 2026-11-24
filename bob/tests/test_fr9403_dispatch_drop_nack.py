"""FR #9403: dispatch miss must NACK / log — not leave chair offered while seat idle."""
from __future__ import annotations

import bob_worker as bw

ASSIGN_A = (
    "FROM jeeves #flamingo flamingo-17160: FR SimonBarnett/bobiverse#9526 "
    "https://github.com/SimonBarnett/bobiverse/issues/9526"
)
ASSIGN_B = (
    "FROM jeeves #flamingo flamingo-17160: FR SimonBarnett/bobiverse#9403 "
    "https://github.com/SimonBarnett/bobiverse/issues/9403"
)


def test_fr9403_second_assign_while_agent_not_ready_nacks():
    logs: list[str] = []
    outbox: list[str] = []
    relay = bw.Relay(log=logs.append, clock=lambda: 100.0)
    relay.write_outbox = lambda text: outbox.append(text) or True
    # No inject target yet.
    relay.set_target(None)
    # First assign: held + ACK path (agent-not-ready hold).
    r1 = relay.deliver("jeeves", "#flamingo", ASSIGN_A)
    assert r1 in ("held", "acked", "injected") or r1 == "held"
    # Second assign while still no inject: must NACK agent-not-ready (FR #9403).
    r2 = relay.deliver("jeeves", "#flamingo", ASSIGN_B)
    assert r2 == "agent_not_ready"
    assert any("agent-not-ready" in x for x in outbox)
    assert any("dispatch-dropped" in x for x in logs)


def test_fr9403_inject_false_on_assign_nacks_inject_failed():
    logs: list[str] = []
    outbox: list[str] = []
    relay = bw.Relay(log=logs.append, clock=lambda: 100.0)
    relay.write_outbox = lambda text: outbox.append(text) or True
    relay.set_target(lambda _line: False)
    # Skip ACK-on-receipt refuse path: prepare_offer no-op, ack always ok.
    relay.prepare_offer = lambda _line: None
    relay.ack_refuse_reason = lambda _payload: None
    result = relay.deliver("jeeves", "#flamingo", ASSIGN_A)
    assert result == "inject_failed"
    assert any("inject failed" in x for x in outbox)
    assert any("dispatch-dropped" in x for x in logs)
