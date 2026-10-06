"""FR #2806: Jeeves 'nothing queued' must start BoredEmitter nak_s (t817u), never reach the agent."""
from __future__ import annotations

import time

import bob_worker as bw
from test_bob_worker_020 import wait_until


class _Seat:
    """Minimal stand-in that only exercises IrcSeat._on_privmsg classification."""

    def __init__(self, nick: str = "marchhare-1", shop: str = "#marchhare"):
        self.nick = nick
        self.machine = "marchhare"
        self.shop = shop
        self.pm_allowed = {"jeeves"}
        self._last_pong = {}
        self.ignored = 0
        self.naks: list[str] = []
        self.msgs: list[tuple[str, str, str]] = []
        self.logs: list[str] = []
        self.on_nak = lambda: self.naks.append("nak")
        self.on_message = lambda s, t, x: self.msgs.append((s, t, x))
        self.log = self.logs.append

    def say(self, *a, **k):
        return None

    def _raw(self, *a, **k):
        return None

    _on_privmsg = bw.IrcSeat._on_privmsg


def test_addressed_nothing_queued_starts_nak_not_message():
    seat = _Seat()
    seat._on_privmsg("Jeeves", "#marchhare", "marchhare-1: nothing queued")
    assert seat.naks == ["nak"]
    assert seat.msgs == []
    assert any("nothing queued from Jeeves" in m for m in seat.logs)


def test_pm_nothing_queued_starts_nak():
    seat = _Seat()
    seat._on_privmsg("Jeeves", "marchhare-1", "nothing queued")
    assert seat.naks == ["nak"]
    assert seat.msgs == []


def test_other_seat_nothing_queued_ignored():
    seat = _Seat()
    seat._on_privmsg("Jeeves", "#marchhare", "marchhare-2: nothing queued")
    assert seat.naks == []
    assert seat.msgs == []


def test_non_jeeves_nothing_queued_ignored():
    seat = _Seat()
    seat._on_privmsg("marchhare-2", "#marchhare", "marchhare-1: nothing queued")
    seat._on_privmsg("bob-ionos", "#marchhare", "marchhare-1: nothing queued")
    assert seat.naks == []
    assert seat.msgs == []


def test_nothing_queued_never_injected_by_relay():
    logs: list[str] = []
    injected: list[str] = []
    r = bw.Relay(log=logs.append, clock=lambda: 0.0)
    r.inject = lambda line: injected.append(line) or True  # type: ignore[method-assign]
    assert r.deliver("Jeeves", "#marchhare", "marchhare-1: nothing queued") == "skipped"
    assert injected == []
    assert any("skipped nothing-queued" in m for m in logs)


def test_inbound_kind_nothing_queued_is_nak():
    assert bw.inbound_kind("marchhare-1: nothing queued", "marchhare-1") == "nak"
    assert bw.inbound_kind("nothing queued", "marchhare-1") == "nak"
    # Other seat address left in place → not stripped as own → agent (accept_for_agent gates it out).
    assert bw.inbound_kind("marchhare-2: nothing queued", "marchhare-1") == "agent"


def test_nak_timer_fires_at_nak_s_after_nothing_queued():
    sent: list = []
    e = bw.BoredEmitter(
        lambda: sent.append(time.monotonic()) or True,
        lambda m: None,
        idle_s=30.0,
        repeat_s=30.0,
        nak_s=0.4,
        harvest_hold_s=0.0,
    )
    e.start()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)  # start
    t = time.monotonic()
    e.nak()  # as on_nak from nothing-queued
    assert not wait_until(lambda: len(sent) > 1, 0.1)
    assert wait_until(lambda: len(sent) == 2, 1.0)
    assert 0.35 <= sent[-1] - t <= 0.7
    assert e.sent[-1][1] == "nak"
    e.stop()


def test_busy_drops_nak_timer_from_nothing_queued():
    sent: list = []
    e = bw.BoredEmitter(
        lambda: sent.append(time.monotonic()) or True,
        lambda m: None,
        idle_s=30.0,
        repeat_s=30.0,
        nak_s=0.3,
        ack_stale_s=60.0,
        harvest_hold_s=0.0,
    )
    e.start()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK FR o/r#7 working")
    e.nak()
    time.sleep(0.8)
    assert len(sent) == 1, "busy at NAK due: nothing sent"
    e.stop()


def test_real_nak_path_unchanged():
    seat = _Seat()
    seat._on_privmsg("Jeeves", "#marchhare", "marchhare-1: NAK !BORED busy")
    assert seat.naks == ["nak"]
    assert seat.msgs == []
    assert any("NAK from Jeeves" in m for m in seat.logs)
