"""t770u: the worker exe posts `!bored` exactly like the agent watcher (Watch-AgentHealth FR #100) - by itself, never the model,
only when idle, same channel/format, same throttle; ACK = busy, DONE = idle (and an immediate !bored); never after IRC loss."""
from __future__ import annotations

import threading
import time

import bob_worker as bw
from repo_layout import ROOT
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
    """FR #161: GIVEUP/NACK clear busy and post !bored immediately (reason=free), with a free-rx log line."""
    sent: list = []
    logs: list = []
    e = bw.BoredEmitter(lambda: sent.append(time.monotonic()) or True, logs.append, idle_s=IDLE, repeat_s=REPEAT, ack_stale_s=60.0)
    e.start()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK UAT o/r#4")
    time.sleep(0.2)
    n = len(sent)
    t = time.monotonic()
    e.on_outbox("GIVEUP UAT o/r#4")
    assert wait_until(lambda: len(sent) == n + 1, 1.0)
    assert sent[-1] - t < 0.2, "GIVEUP -> !bored must be immediate like DONE"
    assert e.sent[-1][1] == "free"
    assert any("free-rx matched (GIVEUP)" in m for m in logs)
    e.on_outbox("ACK FR o/r#5")
    time.sleep(0.1)
    n2 = len(sent)
    e.on_outbox("NACK FR o/r#5")
    assert wait_until(lambda: len(sent) == n2 + 1, 1.0)
    assert e.sent[-1][1] == "free"
    assert any("free-rx matched (NACK)" in m for m in logs)
    e.stop()


def test_drain_applies_job_bookkeeping_when_say_fails(tmp_path):
    """FR #161: if irc.say fails, still apply ACK/DONE/NACK/GIVEUP busy bookkeeping so !bored can fire."""
    sent: list = []
    logs: list = []

    class FailSay:
        shop = "#marchhare"

        def say(self, target, text):
            return False

    e = bw.BoredEmitter(lambda: sent.append(time.monotonic()) or True, logs.append, idle_s=IDLE, repeat_s=REPEAT, ack_stale_s=60.0)
    e.start()
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    ob = tmp_path / "outbox.txt"
    ob.write_text("PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#161\n", encoding="utf-8")
    assert bw.drain_outbox(ob, FailSay(), logs.append, e.on_outbox) == 0
    assert any("say failed; applied busy bookkeeping for ACK" in m for m in logs)
    time.sleep(IDLE + REPEAT + 0.2)
    assert len(sent) == 1, "failed ACK must still mark the seat busy"
    ob.write_text("PRIVMSG #marchhare :GIVEUP FR SimonBarnett/bobiverse#161\n", encoding="utf-8")
    t = time.monotonic()
    assert bw.drain_outbox(ob, FailSay(), logs.append, e.on_outbox) == 0
    assert any("say failed; applied busy bookkeeping for GIVEUP" in m for m in logs)
    assert any("free-rx matched (GIVEUP)" in m for m in logs)
    assert wait_until(lambda: len(sent) >= 2, 1.0)
    assert sent[-1] - t < 0.25
    assert e.sent[-1][1] == "free"
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

# ------------------------------------------------------------------------------------------------ t817u: !bored / NAK are the exe's business
import pytest  # noqa: E402


@pytest.mark.parametrize("text,kind", [
    ("NAK !BORED wait", "nak"), ("marchhare-4242: NAK !BORED wait", "nak"), ("marchhare-4242, nack nothing for you", "nak"),
    ("NACK x", "nak"), ("!bored", "bored"), ("marchhare-4242: !bored", "bored"), ("!BORED", "bored"),
    ("marchhare-4242: FR o/r#1 https://x", "agent"), ("please nak this typo", "agent"), ("naked truth", "agent"),
    ("marchhare-4242: UAT o/r#2 https://x", "agent"), ("boredom is relative", "agent"),
])
def test_inbound_kind(text, kind):
    assert bw.inbound_kind(text, "marchhare-4242") == kind


def test_relay_never_injects_bored_or_nak_lines_from_anyone():
    for t in ("!bored", "NAK !BORED wait", "NACK x", "marchhare-1: NAK !BORED wait", "w-2: !bored", "nak"):
        assert bw.drop_text(t), t
    for t in ("marchhare-1: FR o/r#1 https://x", "do the thing", "naked"):
        assert not bw.drop_text(t), t


def test_seat_swallows_bored_and_nak_and_runs_the_nak_timer_only_for_a_jeeves_nak_addressed_to_it(ircd):
    seat = make_seat(ircd)
    got, naks = [], []
    seat.on_message = lambda n, t, x: got.append(x)
    seat.on_nak = lambda: naks.append(time.monotonic())
    seat.connect(timeout=5)
    ircd.send(":marchhare-3556!w@h PRIVMSG #marchhare :!bored")                       # another worker's !bored
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :NAK !BORED wait")                       # unaddressed NAK: not ours
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :marchhare-3556: NAK !BORED wait")       # NAK for another worker
    ircd.send(":marchhare-3556!w@h PRIVMSG #marchhare :marchhare-4242: NAK !BORED")    # NAK from a non-Jeeves
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :marchhare-4242: !bored")                # even Jeeves-addressed !bored
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :marchhare-4242: NAK !BORED wait")       # THE one: Jeeves NAK to me
    ircd.send(":Jeeves!j@h PRIVMSG marchhare-4242 :nack not now")                      # PM NAK to me
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :marchhare-4242: FR o/r#5 https://x")    # a real assignment still reaches the model
    assert wait_until(lambda: got == ["marchhare-4242: FR o/r#5 https://x"])
    assert len(naks) == 2
    seat.close()


def test_default_nak_timer_is_a_fixed_120_seconds():
    e = bw.BoredEmitter(lambda: True, lambda m: None)
    assert e.nak_s == 120.0


def test_nak_schedules_one_bored_after_the_fixed_timer_and_a_second_nak_does_not_move_it():
    sent: list = []
    e = emitter(sent, idle_s=30.0, repeat_s=30.0, nak_s=0.4)        # idle logic far away: only the NAK timer can fire
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)                  # start
    t = time.monotonic()
    e.nak()
    time.sleep(0.2)
    e.nak()                                                         # a repeated NAK must not extend the fixed timer
    assert not wait_until(lambda: len(sent) > 1, 0.1)               # not early
    assert wait_until(lambda: len(sent) == 2, 1.0)
    assert 0.35 <= sent[-1] - t <= 0.7, sent[-1] - t
    assert e.sent[-1][1] == "nak"
    time.sleep(0.6)
    assert len(sent) == 2                                           # one-shot: no repeat from the NAK timer
    e.stop()


def test_nak_timer_never_sends_while_busy():
    sent: list = []
    e = emitter(sent, idle_s=30.0, repeat_s=30.0, nak_s=0.3, ack_stale_s=60.0)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.on_outbox("ACK FR o/r#7 working")                              # busy
    e.nak()
    time.sleep(0.8)
    assert len(sent) == 1, "busy at the NAK due time: nothing sent"
    e.on_outbox("DONE FR o/r#7 PASS http://x")                      # idle again -> the normal DONE !bored, and the stale NAK timer is gone
    assert wait_until(lambda: len(sent) == 2, 1.0)
    time.sleep(0.6)
    assert [r for _, r in e.sent] == ["start", "done"]
    e.stop()


def test_a_regular_bored_satisfies_a_pending_nak_timer():
    sent: list = []
    e = emitter(sent, idle_s=0.2, repeat_s=0.2, nak_s=0.6)
    e.set_ready(True)
    assert wait_until(lambda: len(sent) == 1, 1.0)
    e.nak()
    assert wait_until(lambda: len(sent) >= 2, 1.0)                  # the idle bored fires first (0.2 s)
    assert e.sent[1][1] == "idle"
    time.sleep(0.8)
    assert "nak" not in [r for _, r in e.sent]
    e.stop()


def test_supervisor_wires_the_seat_nak_to_the_emitter():
    src = (ROOT / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "irc.on_nak = self.bored.nak" in src