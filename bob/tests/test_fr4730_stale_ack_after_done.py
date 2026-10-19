"""FR #4730: replayed ACK for an already-DONE/GIVEUP job must not reopen busy or hit IRC."""
from __future__ import annotations

import bob_worker as bw

DONE_X = "DONE MRB SimonBarnett/a-search#4370 PASS https://example.test/pr/4370"
ACK_X = "ACK MRB SimonBarnett/a-search#4370"
GIVEUP_X = "GIVEUP MRB SimonBarnett/a-search#4370 submit-verify failed"
ACK_Y = "ACK FIX SimonBarnett/a-search#4368"
ASSIGN_Y = (
    "flamingo-1: FIX SimonBarnett/a-search#4368 "
    "https://github.com/SimonBarnett/a-search/issues/4368"
)
ASSIGN_X = (
    "flamingo-1: MRB SimonBarnett/a-search#4370 "
    "https://github.com/SimonBarnett/a-search/pull/4370"
)


class FakeIrc:
    shop = "#flamingo"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def say(self, target, text):
        self.sent.append((target, text))
        return True


def _bored(logs=None):
    logs = logs if logs is not None else []
    return bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=lambda: 100.0,
        harvest_hold_s=90.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
    )


def test_replayed_ack_after_done_does_not_reopen_ack_or_busy_block_y():
    """Fail-when: after DONE X, inject Y, then replay ACK X — must not open ACK / busy on X."""
    logs: list[str] = []
    bored = _bored(logs)
    bored.set_ready(True)

    bored.on_outbox(ACK_X)
    assert bored.ack_open is True
    bored.on_outbox(DONE_X)
    assert bored.ack_open is False

    # Fresh inject of Y (re-offer path clears finished only for Y's key).
    bored.note_fresh_assign(ASSIGN_Y)
    bored.activity(mark_work=True)

    bored.on_outbox(ACK_X)
    assert bored.ack_open is False, "stale ACK X must not reopen ACK after DONE X"
    assert bored._ack_job_key is None
    assert any("ignore stale ACK" in m for m in logs), logs

    # Y can still open a real ACK.
    bored.on_outbox(ACK_Y)
    assert bored.ack_open is True
    assert bored._ack_job_key == "FIX SimonBarnett/a-search#4368"


def test_replayed_ack_after_giveup_not_forwarded_to_irc(tmp_path):
    """Fail-when: replayed ACK X after GIVEUP X must not be forwarded as a fresh ACK."""
    logs: list[str] = []
    bored = _bored(logs)
    bored.set_ready(True)
    bored.on_outbox(ACK_X)
    bored.on_outbox(GIVEUP_X)
    assert bored.ack_open is False
    assert bored.should_forward_outbox(ACK_X) is False

    path = tmp_path / "outbox.txt"
    path.write_text(f"PRIVMSG #flamingo :{ACK_X}\n", encoding="utf-8")
    irc = FakeIrc()
    payloads: list[str] = []

    def on_payload(p: str) -> None:
        payloads.append(p)
        bored.on_outbox(p)

    n = bw.drain_outbox(
        path, irc, logs.append, on_payload, may_send=bored.should_forward_outbox
    )
    assert n == 0, "stale ACK must not be sent"
    assert irc.sent == []
    assert any("dropped stale" in m for m in logs), logs
    assert payloads == [ACK_X], "bookkeeping still sees the drop"
    assert bored.ack_open is False


def test_reoffer_of_finished_job_may_ack_again():
    """Re-offer of X after DONE X clears the finished mark so a new ACK X is live."""
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK_X)
    bored.on_outbox(DONE_X)
    assert bored.should_forward_outbox(ACK_X) is False

    bored.note_fresh_assign(ASSIGN_X)
    assert bored.should_forward_outbox(ACK_X) is True
    bored.on_outbox(ACK_X)
    assert bored.ack_open is True
    assert bored._ack_job_key == "MRB SimonBarnett/a-search#4370"


def test_reoffer_fix_after_nack_may_ack_again():
    """FIX assign keys share outbox typing (FR #4609); re-offer must clear finished."""
    nack_y = "NACK FIX SimonBarnett/a-search#4368 busy"
    bored = _bored()
    bored.set_ready(True)
    bored.on_outbox(ACK_Y)
    bored.on_outbox(nack_y)
    assert bored.should_forward_outbox(ACK_Y) is False
    bored.note_fresh_assign(ASSIGN_Y)
    assert bored.should_forward_outbox(ACK_Y) is True
    bored.on_outbox(ACK_Y)
    assert bored.ack_open is True
    assert bored._ack_job_key == "FIX SimonBarnett/a-search#4368"


def test_done_then_stale_ack_does_not_make_exe_nack_y_as_busy():
    """Integration: after DONE X + inject Y, stale ACK X must not cause busy NACK of Y."""
    logs: list[str] = []
    outbox: list[str] = []
    injected: list[str] = []
    clock_t = [0.0]

    def clock():
        return clock_t[0]

    bored = bw.BoredEmitter(
        lambda: True,
        logs.append,
        clock=clock,
        harvest_hold_s=1.0,
        idle_s=9999.0,
        repeat_s=9999.0,
        retry_s=0.05,
        assign_grace_s=600.0,
    )
    relay = bw.Relay(log=logs.append, clock=clock, max_pending=8)
    relay.write_outbox = lambda t: outbox.append(t) or True
    relay.set_target(lambda line: injected.append(line) or True)
    relay.hold_assigns_while = lambda: bored.holding_incoming_assigns
    relay.on_hold_assign = lambda line: bored.note_held_assign()
    relay.on_inject = lambda line: (
        bored.note_fresh_assign(line),
        bored.activity(mark_work=True),
    )

    bored.set_ready(True)
    bored.on_outbox(ACK_X)
    bored.on_outbox(DONE_X)
    # End harvest so Y is not parked forever.
    clock_t[0] = 2.0
    with bored._cv:
        bored._harvest_until = None
        bored._held_assign = False

    st = relay.deliver("Jeeves", "#flamingo", ASSIGN_Y)
    assert st == "injected", st
    assert any("a-search#4368" in x for x in injected)

    bored.on_outbox(ACK_X)
    assert bored.ack_open is False
    # No exe busy-hold NACK naming X for Y.
    assert not any("busy, holding" in o and "4370" in o for o in outbox), outbox
    assert not any(o.startswith("NACK FIX") and "busy" in o for o in outbox), outbox
