"""FR #4115: lost-paste recovery - clipboard readback, delayed restore, re-paste once then NACK,
ack-miss repeats the assign, startup inject waits for session ready."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
from test_fr2884_startup_turn_ready import FakeTimer, _sup

ASSIGN = (
    "FROM Jeeves #win-mpre8vi4u6u win-mpre8vi4u6u-3784: MRB SimonBarnett/bobiverse#4116 "
    "https://github.com/SimonBarnett/bobiverse/pull/4116 [outbox: C:\\run\\outbox.txt]"
)


# ---------------------------------------------------------------- 4. clipboard readback + logs
def test_clipboard_readback_ok_logs_and_returns_true():
    logs: list[str] = []
    clip = {}
    ok = bw.clipboard_set_verified(
        "hello", set_fn=lambda t, log=None: clip.update(v=t) or True,
        read_fn=lambda log=None: clip.get("v"), log=logs.append,
    )
    assert ok is True
    assert any("clipboard readback ok chars=5" in m for m in logs)


def test_clipboard_readback_mismatch_falls_back():
    logs: list[str] = []
    ok = bw.clipboard_set_verified(
        "hello", set_fn=lambda t, log=None: True, read_fn=lambda log=None: "rdpclip-other", log=logs.append
    )
    assert ok is False
    assert any("readback mismatch" in m for m in logs)


def test_clipboard_set_or_read_failure_falls_back():
    logs: list[str] = []
    assert not bw.clipboard_set_verified("x", set_fn=lambda t, log=None: False, read_fn=lambda log=None: "x", log=logs.append)
    assert not bw.clipboard_set_verified("x", set_fn=lambda t, log=None: True, read_fn=lambda log=None: None, log=logs.append)
    assert any("readback fail reason=set" in m for m in logs)
    assert any("readback fail reason=read" in m for m in logs)


def test_inject_console_uses_verified_set_and_delayed_restore_source():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    inj = src[src.index("def inject_console"):]
    inj = inj[: inj.index("\ndef send_console_enter")]
    assert "clipboard_set_verified(" in inj
    assert "schedule_clipboard_restore(" in inj
    # never restore synchronously right after the 0.2 s gap again
    assert "_clipboard_restore_unicode(prior, log=log)\n" not in inj
    assert "inject path=keys reason=clipboard_fallback" in inj
    assert "inject path=paste" in inj


def test_delayed_restore_only_when_clipboard_still_ours():
    restored: list = []
    timers: list = []

    class T:
        def __init__(self, d, fn):
            self.d, self.fn, self.daemon = d, fn, False
            timers.append(self)

        def start(self):
            pass

    cur = {"v": "ours"}
    bw.schedule_clipboard_restore("prior", "ours", delay_s=8, read_fn=lambda log=None: cur["v"],
                                  restore_fn=lambda p, log=None: restored.append(p) or True, timer_cls=T)
    assert timers[0].d == 8
    timers[0].fn()
    assert restored == ["prior"]
    cur["v"] = "operator copied something"
    bw.schedule_clipboard_restore("prior", "ours", delay_s=8, read_fn=lambda log=None: cur["v"],
                                  restore_fn=lambda p, log=None: restored.append(p) or True, timer_cls=T)
    timers[1].fn()
    assert restored == ["prior"]  # not clobbered


# ---------------------------------------------------------------- 1. re-paste once, then NACK
def test_submit_verify_failed_calls_on_failed_only_on_failure():
    calls: list[str] = []
    t = {"now": 0.0}

    def clock():
        return t["now"]

    def sleep(s):
        t["now"] += s

    bw.inject_with_submit_verify(1, "x", inject_fn=lambda pid, text, log=None: True, enter_fn=lambda *a: True,
                                 probe_fn=lambda: False, clock=clock, sleep=sleep, verify_s=0.1, max_retries=1,
                                 backoffs=(0.1,), sync=True, on_failed=lambda: calls.append("failed"))
    assert calls == ["failed"]
    bw.inject_with_submit_verify(1, "x", inject_fn=lambda pid, text, log=None: True, enter_fn=lambda *a: True,
                                 probe_fn=lambda: True, clock=clock, sleep=sleep, verify_s=0.1, max_retries=1,
                                 backoffs=(0.1,), sync=True, on_failed=lambda: calls.append("failed"))
    assert calls == ["failed"]


def _recovery(reinject_ok=True, acked=False):
    state = {"reinjects": [], "outbox": [], "cleared": [], "logs": []}

    def reinject(line, cb):
        state["reinjects"].append(line)
        state["cb"] = cb
        return reinject_ok

    rec = bw.InjectRecovery(
        reinject=reinject,
        write_outbox=lambda text: state["outbox"].append(text) or True,
        clear_local=lambda line: state["cleared"].append(line),
        is_acked=lambda line: acked,
        log=state["logs"].append,
    )
    return rec, state


def test_first_failure_repastes_full_assign_once():
    rec, st = _recovery()
    assert rec.on_failed(ASSIGN) == "retried"
    assert st["reinjects"] == [ASSIGN]
    assert st["outbox"] == []
    # second failure (callback from the re-paste) NACKs and clears
    assert st["cb"]() == "nacked"
    assert st["reinjects"] == [ASSIGN]  # no third paste
    assert st["outbox"] == ["NACK MRB SimonBarnett/bobiverse#4116 inject failed"]
    assert st["cleared"] == [ASSIGN]


def test_repaste_that_cannot_start_nacks_immediately():
    rec, st = _recovery(reinject_ok=False)
    assert rec.on_failed(ASSIGN) == "nacked"
    assert st["outbox"] == ["NACK MRB SimonBarnett/bobiverse#4116 inject failed"]


def test_acked_job_and_non_assign_are_left_alone():
    rec, st = _recovery(acked=True)
    assert rec.on_failed(ASSIGN) == "acked"
    rec2, st2 = _recovery()
    assert rec2.on_failed("FROM bob-worker #x Reminder: ACK/DONE must go to $env:BOB_OUTBOX") == "ignored"
    assert st["outbox"] == [] and st2["outbox"] == [] and st2["reinjects"] == []


def test_nack_line_and_outbox_append(tmp_path):
    assert bw.assign_job_key(ASSIGN) == "MRB SimonBarnett/bobiverse#4116"
    assert bw.inject_failed_nack_line(ASSIGN) == "NACK MRB SimonBarnett/bobiverse#4116 inject failed"
    assert bw.inject_failed_nack_line("FROM Jeeves #x y: nothing queued") is None
    ob = tmp_path / "outbox.txt"
    ob.write_text("ACK FR a/b#1\n", encoding="utf-8")
    assert bw.append_outbox_line(ob, "NACK MRB a/b#2 inject failed")
    assert ob.read_text(encoding="utf-8").splitlines() == ["ACK FR a/b#1", "NACK MRB a/b#2 inject failed"]


def test_supervisor_recovery_writes_nack_to_run_dir_outbox(tmp_path, monkeypatch):
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    sup.ack_miss.note_inject(ASSIGN, 0.0, own_nick=sup.nick)
    relay.last_unacked = ASSIGN
    res = sup._inject_recovery().on_failed(ASSIGN, attempt=2)
    assert res == "nacked"
    ob = bw.outbox_path_for_run(tmp_path)
    assert "NACK MRB SimonBarnett/bobiverse#4116 inject failed" in ob.read_text(encoding="utf-8")
    assert sup.ack_miss.last_line == ""  # cleared locally: no ack-miss recycle for a NACKed job
    assert relay.last_unacked == ""


# ---------------------------------------------------------------- 2. ack-miss repeats the assign
def test_ack_miss_reminder_repeats_pending_assign():
    am = bw.AssignAckMiss(remind_s=180, recycle_s=900)
    am.note_inject(ASSIGN, 0.0, own_nick="win-mpre8vi4u6u-3784")
    assert am.tick(181.0, ack_open=False) == "remind"
    assert am.reminder_line(shop="#win-mpre8vi4u6u", outbox="C:\\run\\outbox.txt") == ASSIGN


def test_ack_miss_reminder_generic_without_assign():
    am = bw.AssignAckMiss(remind_s=180, recycle_s=900)
    line = am.reminder_line(shop="#s", outbox="C:\\run\\outbox.txt")
    assert "Reminder: ACK/DONE must go to $env:BOB_OUTBOX" in line


# ---------------------------------------------------------------- 3. startup waits for session ready
def test_startup_grace_does_not_release_grok_before_turn_ended(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_WORKER_STARTUP_WAIT_READY", raising=False)
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "900")
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    clock["t"] = 60.0
    FakeTimer.instances[0].fn()  # grace expiry
    assert not any("agent: ready" in m for m in logs)
    assert any("session not ready" in m and "cap 900s" in m for m in logs)
    assert "ready" not in sup.bored.fires
    cap_timer = FakeTimer.instances[-1]
    assert cap_timer.delay == 840.0
    # first turn_ended releases and cancels the cap timer
    clock["t"] = 120.0
    sup._maybe_ready_on_first_turn_ended(sup.sessions[-1])
    assert any("first turn_ended" in m for m in logs)
    assert "ready" in sup.bored.fires
    assert cap_timer.cancelled


def test_startup_cap_releases_when_turn_never_ends(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_WORKER_STARTUP_WAIT_READY", raising=False)
    monkeypatch.setenv("BOB_WORKER_STARTUP_READY_CAP_S", "600")
    sup, logs, clock, injected, relay = _sup(tmp_path, monkeypatch)
    assert sup.start_agent()
    FakeTimer.instances[0].fn()
    FakeTimer.instances[-1].fn()  # cap
    assert any("startup ready cap 600s" in m for m in logs)
    assert "ready" in sup.bored.fires


# ---------------------------------------------------------------- 5. Grok prompt-accept timeout
TOAST = (
    "  The agent did not accept your prompt within 120s. Your text is back in the input box; "
    "press Enter to retry\n  > MRB SimonBarnett/bobiverse#4116 ...\n  Prompt not accepted, text restored"
)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _pw(screens, clock, enters, gave, backoffs=(15.0, 30.0, 60.0)):
    it = iter(screens)
    box = {"cur": None}

    def read():
        try:
            box["cur"] = next(it)
        except StopIteration:
            pass
        return box["cur"]

    logs: list[str] = []
    w = bw.PromptNotAcceptedWatcher(
        read_fn=read, enter_fn=lambda: enters.append(clock.t) or True,
        on_give_up=lambda: gave.append(clock.t), clock=clock, log=logs.append, backoffs=backoffs,
    )
    return w, logs


def test_prompt_not_accepted_regex_matches_grok_texts():
    assert bw.PROMPT_NOT_ACCEPTED_RX.search("Prompt not accepted, text restored")
    assert bw.PROMPT_NOT_ACCEPTED_RX.search("The agent did not accept your prompt within 120s.")
    assert not bw.PROMPT_NOT_ACCEPTED_RX.search("Waiting for response 0.0s")


def test_prompt_not_accepted_enters_with_backoff_then_gives_up_once():
    clock, enters, gave = _Clock(), [], []
    w, logs = _pw([TOAST] * 20, clock, enters, gave)
    assert w.tick() == "enter" and enters == [0.0]
    clock.t = 10
    assert w.tick() == "wait"
    clock.t = 15
    assert w.tick() == "enter"
    clock.t = 45
    assert w.tick() == "enter"
    assert len(enters) == 3
    clock.t = 104
    assert w.tick() == "wait"
    clock.t = 105
    assert w.tick() == "gave_up" and gave == [105]
    clock.t = 500
    assert w.tick() == "done" and gave == [105]
    assert len(enters) == 3
    assert any("Enter retry 1/3" in m for m in logs)
    assert any("giving up" in m for m in logs)


def test_prompt_not_accepted_clears_when_toast_gone():
    clock, enters, gave = _Clock(), [], []
    w, logs = _pw([TOAST, "  > working...\n  Waiting for response 1.2s"], clock, enters, gave)
    assert w.tick() == "enter"
    clock.t = 20
    assert w.tick() == "clear"
    assert gave == [] and w.tries == 0 and not w.active
    assert any("cleared after 1 Enter" in m for m in logs)


def test_prompt_not_accepted_stale_text_ignored_after_turn_activity():
    clock, enters, gave = _Clock(), [], []
    w, logs = _pw([TOAST] * 5, clock, enters, gave)
    assert w.tick() == "enter"
    w.note_activity()  # turn started: prompt went through; toast is now stale scrollback
    clock.t = 100
    assert w.tick() == "stale"
    assert w.tick() == "stale"
    assert enters == [0.0] and gave == []


def test_prompt_not_accepted_no_screen_is_noop():
    clock, enters, gave = _Clock(), [], []
    w, _ = _pw([None], clock, enters, gave)
    assert w.tick() == "clear" and enters == []


def test_prompt_retry_backoffs_env(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_PROMPT_RETRY_BACKOFFS", "5,10")
    assert bw._prompt_retry_backoffs() == (5.0, 10.0)
    monkeypatch.setenv("BOB_WORKER_PROMPT_RETRY_BACKOFFS", "junk")
    assert bw._prompt_retry_backoffs() == (15.0, 30.0, 60.0)


def test_prompt_give_up_nacks_pending_assign(tmp_path, monkeypatch):
    sup, *_ = _sup(tmp_path, monkeypatch)
    calls = []

    class _Rec:
        def on_failed(self, line, attempt=1):
            calls.append((line, attempt))
            return "nacked"

    sup._recovery = _Rec()
    sup.ack_miss.last_line = ASSIGN
    sup._prompt_give_up()
    assert calls == [(ASSIGN, 2)]


def test_prompt_give_up_without_assign_only_logs(tmp_path, monkeypatch):
    sup, *_ = _sup(tmp_path, monkeypatch)
    calls = []

    class _Rec:
        def on_failed(self, line, attempt=1):
            calls.append(line)

    sup._recovery = _Rec()
    sup.ack_miss.last_line = ""
    with __import__("contextlib").suppress(Exception):
        sup.relay.last_unacked = ""
    sup._prompt_give_up()
    assert calls == []
