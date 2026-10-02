"""t770u: the worker exe posts `!bored` exactly like the agent watcher (Watch-AgentHealth FR #100) - by itself, never the model,
only when idle, same channel/format, same throttle; ACK = busy, DONE = idle (and an immediate !bored); never after IRC loss."""
from __future__ import annotations

import threading
import time

import bob_worker as bw
from test_bob_worker_020 import Rig, ircd, make_seat, wait_until  # noqa: F401  (ircd is a fixture)

IDLE, REPEAT = 0.3, 0.5


def emitter(sent, **kw):
    kw.setdefault("idle_s", IDLE)
    kw.setdefault("repeat_s", REPEAT)
    kw.setdefault("ack_stale_s", 60.0)
    e = bw.BoredEmitter(lambda: sent.append(time.monotonic()) or True, lambda m: None, **kw)
    e.start()
    return e


# ------------------------------------------------------------------------------------------------ the rules (emitter alone)
def test_bored_is_sent_on_start_then_while_idle_with_the_watcher_throttle():
    sent: list = []
    e = emitter(sent)
    t0 = time.monotonic()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) >= 1, 1.0)
    assert sent[0] - t0 < 0.25, "start: immediately, not after a poll tick"
    assert wait_until(lambda: len(sent) >= 4, 3.0)
    gaps = [b - a for a, b in zip(sent, sent[1:])]
    assert gaps[0] >= IDLE * 0.9                                   # first idle after the start: idle window
    assert all(g >= REPEAT * 0.9 for g in gaps[1:]), gaps          # then the repeat window, never faster
    assert [r for _, r in e.sent][:2] == ["start", "idle"]
    e.stop()


def test_bored_is_never_sent_while_busy_and_done_triggers_it_immediately():
    sent: list = []
    e = emitter(sent)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK FR SimonBarnett/bobiverse#7 fix the thing")   # Jeeves assigned a job: busy
    time.sleep(IDLE + REPEAT + 0.3)
    assert len(sent) == 1, "busy (open ACK) must silence !bored"
    n = len(sent)
    t = time.monotonic()
    e.on_outbox("DONE FR SimonBarnett/bobiverse#7 PASS https://github.com/SimonBarnett/bobiverse/pull/9")
    assert wait_until(lambda: len(sent) == n + 1, 1.0)
    assert sent[-1] - t < 0.2, "DONE -> !bored must be immediate (watcher gate: ~5 s)"
    assert e.sent[-1][1] == "done"
    time.sleep(0.2)
    assert [r for _, r in e.sent].count("done") == 1               # the same DONE never re-fires
    e.stop()


def test_a_busy_agent_is_silent_when_it_is_not_ready_or_the_ack_is_fresh_but_stale_acks_expire():
    sent: list = []
    e = emitter(sent, ack_stale_s=0.6)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK MRB o/r#3")
    time.sleep(0.45)
    e.on_outbox("progress note")                                    # outbox activity keeps a live ACK fresh (watcher: mtime)
    time.sleep(0.45)
    assert len(sent) == 1
    assert wait_until(lambda: len(sent) >= 2, 3.0), "an ACK with no DONE and no activity goes stale and the seat is idle again"
    n = len(sent)
    e.set_ready(False)                                              # agent restarting / hung: not idle
    time.sleep(IDLE + REPEAT)
    assert len(sent) == n
    e.stop()


def test_nack_and_giveup_free_the_seat():
    sent: list = []
    e = emitter(sent)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK UAT o/r#4")
    time.sleep(0.2)
    e.on_outbox("GIVEUP UAT o/r#4")
    assert wait_until(lambda: len(sent) >= 2, 2.0)
    e.stop()


def test_forwarded_work_resets_the_idle_clock():
    sent: list = []
    e = emitter(sent)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    for _ in range(6):                                              # a forward every 0.1 s: never idle for 0.3 s
        time.sleep(0.1)
        e.activity()
    assert len(sent) == 1
    e.stop()


def test_stopped_emitter_never_sends_again():
    sent: list = []
    e = emitter(sent)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.stop()
    e.on_outbox("DONE FR o/r#1 PASS http://x")
    time.sleep(IDLE + REPEAT)
    assert len(sent) == 1


def test_failed_send_is_retried_later_not_in_a_tight_loop():
    calls: list = []
    e = bw.BoredEmitter(lambda: calls.append(time.monotonic()) or False, lambda m: None, idle_s=IDLE, repeat_s=REPEAT, retry_s=0.3)
    e.start()
    e.set_ready(True)
    time.sleep(1.0)
    e.stop()
    assert 1 <= len(calls) <= 5, calls


# ------------------------------------------------------------------------------------------------ on the wire (fake IRC, real seat + supervisor)
def bored_lines(ircd):
    return [r for r in ircd.received if r == "PRIVMSG #marchhare :!bored"]


def rig_with_bored(ircd, tmp_path):
    seat = make_seat(ircd)
    rig = Rig(tmp_path, irc=seat)
    seat.log = rig.logs.append
    seat.on_message = rig.relay.deliver
    seat.connect(timeout=5)
    rig.sup.bored = bw.BoredEmitter(rig.sup.post_bored, rig.logs.append, idle_s=IDLE, repeat_s=REPEAT)
    rig.sup.bored.start()
    return seat, rig


def test_wire_bored_goes_to_own_shop_in_watcher_format_when_the_agent_is_ready(ircd, tmp_path):
    seat, rig = rig_with_bored(ircd, tmp_path)
    assert not bored_lines(ircd)
    rig.sup.start_agent()                                           # agent ready (grace 0) -> start trigger
    assert wait_until(lambda: len(bored_lines(ircd)) >= 1, 2.0)
    assert not any("!bored" in r and not r.startswith("PRIVMSG #marchhare :") for r in ircd.received)
    rig.sup.shutdown("test", bw.EXIT_OK)


def test_wire_ack_silences_done_resumes_and_the_model_cannot_post_bored(ircd, tmp_path):
    seat, rig = rig_with_bored(ircd, tmp_path)
    rig.sup.start_agent()
    assert wait_until(lambda: len(bored_lines(ircd)) == 1, 2.0)
    ob = tmp_path / "outbox.txt"
    ob.write_text("PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#7\nPRIVMSG #marchhare :!bored\n!bored\n", encoding="utf-8")
    bw.drain_outbox(ob, seat, rig.logs.append, rig.sup.bored.on_outbox)
    assert wait_until(lambda: "PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#7" in ircd.received, 2.0)
    time.sleep(IDLE + REPEAT + 0.2)
    assert len(bored_lines(ircd)) == 1, "no !bored while the ACKed job is open, and the model's own !bored lines are refused"
    assert any("refused agent-written !bored" in m for m in rig.logs)
    ob.write_text("PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#7 PASS https://github.com/SimonBarnett/bobiverse/pull/9\n", encoding="utf-8")
    bw.drain_outbox(ob, seat, rig.logs.append, rig.sup.bored.on_outbox)
    assert wait_until(lambda: len(bored_lines(ircd)) == 2, 2.0)
    rig.sup.shutdown("test", bw.EXIT_OK)


def test_wire_no_bored_after_irc_loss(ircd, tmp_path):
    seat, rig = rig_with_bored(ircd, tmp_path)
    rig.sup.start_agent()
    assert wait_until(lambda: len(bored_lines(ircd)) == 1, 2.0)
    result: list = []
    threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
    ircd.drop()
    assert wait_until(lambda: result == [bw.EXIT_IRC_LOST], 3.0)
    n_wire, n_sent = len(bored_lines(ircd)), len(rig.sup.bored.sent)
    assert rig.sup.post_bored() is False                           # the only send path refuses after a loss
    rig.sup.bored.on_outbox("DONE FR o/r#1 PASS http://x")
    time.sleep(IDLE + REPEAT + 0.2)
    assert len(bored_lines(ircd)) == n_wire and len(rig.sup.bored.sent) == n_sent


def test_wire_agent_restart_is_not_idle_so_no_bored_until_the_new_agent_is_ready(ircd, tmp_path):
    seat, rig = rig_with_bored(ircd, tmp_path)
    rig.sup.start_agent()
    assert wait_until(lambda: len(bored_lines(ircd)) == 1, 2.0)
    rig.sup.bored.set_ready(False)
    time.sleep(IDLE + REPEAT)
    assert len(bored_lines(ircd)) == 1
    rig.sup.shutdown("test", bw.EXIT_OK)