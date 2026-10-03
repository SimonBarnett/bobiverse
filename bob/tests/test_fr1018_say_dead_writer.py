"""FR #1018: IrcSeat.say() must return False when the writer thread is dead."""
from __future__ import annotations

import threading
import time

import bob_worker as bw
from test_bob_worker_020 import ircd, make_seat, wait_until  # noqa: F401


def test_say_returns_false_when_writer_thread_dead():
    lost: list[str] = []
    seat = bw.IrcSeat("127.0.0.1", 1, "marchhare-1", "marchhare", tls=False, log=lambda m: None)
    seat.on_lost = lambda why: lost.append(why)
    seat.sock = object()  # pretend connected
    seat._stop.clear()
    seat._lost_once = False
    # Dead writer: thread object that never started / already finished
    dead = threading.Thread(target=lambda: None, name="irc-write-dead")
    dead.start()
    dead.join(1.0)
    seat._writer = dead
    assert seat.say("#marchhare", "!bored") is False
    assert lost and "writer" in lost[0]


def test_write_loop_oserror_marks_lost(ircd):
    seat = make_seat(ircd)
    lost: list[str] = []
    seat.on_lost = lambda why: lost.append(why)
    seat.connect(timeout=5)

    def boom(_line):
        raise OSError("broken pipe")

    seat._raw = boom  # type: ignore[method-assign]
    assert seat.say(seat.shop, "ping-test") is True  # enqueued while writer still alive
    assert wait_until(lambda: bool(lost), 2.0), lost
    assert seat.say(seat.shop, "again") is False
    seat.close()
