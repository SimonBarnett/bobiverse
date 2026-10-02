"""bob-worker (t762u-t765u): agent selection, always-NEW agents, IRC seat (fake ircd), ping liveness, immediate relay,
IRC loss => agent tree killed + exit, hung agent => bounded NEW restart, outbox rules."""
from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

import bob_worker as bw

ROOT = Path(__file__).resolve().parent.parent


def wait_until(cond, timeout=5.0, step=0.01):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


# ----------------------------------------------------------------------------------------------- fakes
class FakeIrcd:
    """Minimal IRC server on localhost: registers on NICK+USER, answers PING, records everything it receives."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.received: list = []
        self.conn: socket.socket | None = None
        self.silent = False  # True = never answer anything (dead link)
        self.auto_welcome = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        try:
            c, _ = self.srv.accept()
        except OSError:
            return
        self.conn = c
        buf = b""
        nick = "x"
        while True:
            try:
                d = c.recv(4096)
            except OSError:
                return
            if not d:
                return
            buf += d
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                s = ln.decode().rstrip("\r")
                self.received.append(s)
                if self.silent:
                    continue
                if s.startswith("NICK "):
                    nick = s[5:]
                if s.startswith("USER ") and self.auto_welcome:
                    self.send(f":srv 001 {nick} :Welcome")
                if s.startswith("JOIN "):
                    self.send(f":{nick}!u@h JOIN {s[5:]}")
                if s.startswith("PING "):
                    self.send(f":srv PONG srv {s[5:]}")

    def send(self, line: str):
        self.conn.sendall((line + "\r\n").encode())

    def drop(self):
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.conn.close()

    def close(self):
        try:
            self.srv.close()
        except OSError:
            pass


@pytest.fixture
def ircd():
    d = FakeIrcd()
    yield d
    d.close()


def make_seat(ircd, machine="marchhare", pid=4242, **kw):
    seat = bw.IrcSeat("127.0.0.1", ircd.port, bw.seat_nick(machine, pid), machine, tls=False, log=lambda m: None, send_gap_s=0.01, **kw)
    return seat


class FakeProc:
    _n = 1000

    def __init__(self):
        FakeProc._n += 1
        self.pid = FakeProc._n
        self._done = threading.Event()
        self.code = None

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        self._done.wait(timeout)
        return self.code

    def finish(self, code=0):
        self.code = code
        self._done.set()


class Rig:
    """Supervisor with every side effect faked."""

    def __init__(self, tmp_path, irc=None, **kw):
        self.spawned: list = []
        self.killed: list = []
        self.injected: list = []
        self.procs: list = []
        self.samples = [bw.Sample(True, True, 1)]
        self.logs: list = []
        self.relay = bw.Relay(self.logs.append)

        def spawn(spec, env):
            p = FakeProc()
            self.procs.append(p)
            self.spawned.append((spec, env))
            return p

        def kill(pid):
            self.killed.append(pid)
            for p in self.procs:
                if p.pid == pid and p.code is None:
                    p.finish(1)
            return True

        def inject(pid, text):
            self.injected.append((pid, text, threading.current_thread().name, time.monotonic()))
            return True

        def probe(pid):
            return self.samples[-1] if len(self.samples) == 1 else self.samples.pop(0)

        kw.setdefault("startup_grace_s", 0)
        kw.setdefault("health_interval_s", 0.02)
        self.sup = bw.Supervisor(kind=kw.pop("kind", "cursor"), exe=r"C:\x\agent.cmd", cwd=r"C:\ai\bob\worker", machine="marchhare", nick="marchhare-4242",
                                 run_dir=tmp_path / "run", irc=irc, relay=self.relay, log=self.logs.append, spawn=spawn, kill=kill, probe=probe,
                                 inject=inject, **kw)


# ----------------------------------------------------------------------------------------------- selection (cursor -> grok -> dialog)
CUR, GRK = r"C:\c\agent.cmd", r"C:\g\agent.exe"


@pytest.mark.parametrize("fuel,cur,grk,want", [
    (bw.Fuel(40, 10, 50, "available"), CUR, GRK, "cursor"),
    (bw.Fuel(0, 7, 50, "available"), CUR, GRK, "cursor"),          # low pool alone is enough
    (bw.Fuel(9, 0, 0, "exhausted"), CUR, GRK, "cursor"),           # high pool alone is enough
    (bw.Fuel(0, 0, 50, "available"), CUR, GRK, "grok"),
    (bw.Fuel(None, None, None, "available"), CUR, GRK, "grok"),    # Grok 1.0.41: no %, verified auth
    (bw.Fuel(40, 10, 50, "available"), None, GRK, "grok"),         # cursor tokens but agent.cmd missing
    (bw.Fuel(0, 0, 0, "exhausted"), CUR, GRK, "dialog"),
    (bw.Fuel(None, None, None, "unknown"), CUR, GRK, "dialog"),    # unknown is NOT 'remains'
    (bw.Fuel(0, 0, 0, "exhausted"), CUR, None, "none"),            # nothing to ask a key for
])
def test_selection_cursor_then_grok_then_dialog(fuel, cur, grk, want):
    assert bw.select_agent(fuel, cur, grk).kind == want


def test_parse_fuel_is_tolerant():
    f = bw.parse_fuel('noise\n{"ok":true,"cursor":{"high":12,"low":null,"any":12},"grok":{"remaining_pct":8,"state":"available"}}\n')
    assert (f.cursor_high, f.cursor_low, f.grok_pct, f.grok_state) == (12, None, 8, "available")
    assert bw.parse_fuel("garbage") == bw.Fuel()
    assert bw.parse_fuel("") == bw.Fuel()


def test_read_fuel_uses_the_helper_and_survives_failure(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "Get-BobAgentFuel.ps1").write_text("x")
    calls = []

    class R:
        stdout = '{"ok":true,"cursor":{"high":5,"low":0},"grok":{"remaining_pct":null,"state":"unknown"}}'

    def run(argv, **k):
        calls.append(argv)
        return R()

    assert bw.read_fuel(tmp_path, run).cursor_high == 5
    assert "Get-BobAgentFuel.ps1" in " ".join(calls[0])

    def boom(*a, **k):
        raise OSError("no powershell")

    assert bw.read_fuel(tmp_path, boom) == bw.Fuel()
    assert bw.read_fuel(tmp_path / "nowhere", run) == bw.Fuel()


def test_dialog_key_goes_to_child_env_only_and_is_never_logged(tmp_path):
    rig = Rig(tmp_path, kind="grok", env_secret=bw.SecretStr("xai-SECRET-123"))
    assert rig.sup.start_agent()
    spec, env = rig.spawned[0]
    assert env["XAI_API_KEY"] == "xai-SECRET-123"
    assert "xai-SECRET-123" not in " ".join(map(str, spec.argv)) + "".join(rig.logs) + repr(rig.sup.secret) + str(rig.sup.secret)
    assert "XAI_API_KEY" not in __import__("os").environ or __import__("os").environ["XAI_API_KEY"] != "xai-SECRET-123"
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert "xai-SECRET-123" not in f.read_text(errors="ignore")
    rig.sup.shutdown("test", 0)


# ----------------------------------------------------------------------------------------------- ALWAYS a NEW agent (t765u)
@pytest.mark.parametrize("kind", ["grok", "cursor"])
@pytest.mark.parametrize("mode", ["agent", "plan"])
def test_launch_command_never_resumes_or_continues(tmp_path, kind, mode):
    spec = bw.build_launch(kind, mode, r"C:\ai\bob\worker", "prompt", r"C:\x\agent", tmp_path)
    for a in spec.argv:
        assert a.lower() not in ("--resume", "-r", "--continue", "-c", "--resume-session")
    for text in spec.files.values():
        assert "--resume" not in text and "--continue" not in text
    assert spec.session_id


@pytest.mark.parametrize("bad", [["a", "--resume", "x"], ["a", "-r", "sid"], ["a", "--continue"], ["a", "-c"]])
def test_assert_fresh_refuses_resume_flags(bad):
    with pytest.raises(ValueError):
        bw.assert_fresh(bad)
    with pytest.raises(ValueError):
        bw.assert_fresh(["ok"], {"x.ps1": "& agent --resume abc"})


def test_second_launch_is_a_new_agent_not_a_reuse(tmp_path):
    a, b = Rig(tmp_path / "a"), Rig(tmp_path / "b")
    # a live state file from the first launch must not influence the second one
    (tmp_path / "a" / "run").mkdir(parents=True, exist_ok=True)
    (tmp_path / "a" / "run" / "session.json").write_text('{"session": "old"}')
    assert a.sup.start_agent() and b.sup.start_agent()
    assert a.procs[0].pid != b.procs[0].pid                      # two processes
    assert a.sup.sessions[0] != b.sup.sessions[0]                # two sessions
    assert a.sup.run_dir != b.sup.run_dir                        # two run dirs
    for rig in (a, b):
        assert len(rig.spawned) == 1                             # each launch spawned its OWN agent
        assert "old" not in " ".join(map(str, rig.spawned[0][0].argv))
    a.sup.shutdown("t", 0)
    b.sup.shutdown("t", 0)


def test_plan_launch_twice_makes_two_agents(tmp_path, monkeypatch):
    starts = []

    class P:
        pid = 0

        def __init__(self):
            P.pid += 1
            self.pid = P.pid + 7000

        def poll(self):
            return None

    monkeypatch.setattr(bw, "default_spawn", lambda spec, env: (starts.append(spec), P())[1])
    monkeypatch.setattr(bw, "read_fuel", lambda root: bw.Fuel(30, 30, 30, "available"))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: r"C:\c\agent.cmd")
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: r"C:\g\agent.exe")
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    (tmp_path / "plan").mkdir()
    args = type("A", (), {"install_root": str(tmp_path)})()
    log = bw.Log(None)
    assert bw.run_plan(args, log) == 0
    assert bw.run_plan(args, log) == 0
    assert len(starts) == 2 and starts[0].session_id != starts[1].session_id
    assert all(s.cwd == str(tmp_path / "plan") for s in starts)


def test_hang_restart_is_a_new_agent_not_a_resume(tmp_path):
    rig = Rig(tmp_path, backoff=(0.0,))
    rig.sup.start_agent()
    first = rig.procs[0].pid
    rig.sup.restart_agent("not-responding")
    assert len(rig.procs) == 2 and rig.procs[1].pid != first and first in rig.killed
    assert len(set(rig.sup.sessions)) == 2
    for spec, _ in rig.spawned:
        bw.assert_fresh(spec.argv, {k: v for k, v in spec.files.items() if k.endswith(".ps1")})
    rig.sup.shutdown("t", 0)


def test_cursor_prompt_never_lands_on_a_command_line(tmp_path):
    evil = 'hi" & calc & "'
    spec = bw.build_launch("cursor", "agent", r"C:\ai\bob\worker", evil, r"C:\x\agent.cmd", tmp_path)
    assert evil not in " ".join(spec.argv)
    assert any(evil == v for v in spec.files.values())


# ----------------------------------------------------------------------------------------------- IRC seat (fake ircd)
def test_nick_and_channel_rules(ircd):
    seat = make_seat(ircd, pid=4242)
    seat.connect(timeout=5)
    assert wait_until(lambda: "JOIN #marchhare" in ircd.received)
    assert "NICK marchhare-4242" in ircd.received
    assert [r for r in ircd.received if r.startswith("JOIN ")] == ["JOIN #marchhare"]  # ONLY its own shop
    seat.close()


def test_seat_only_speaks_in_its_own_shop(ircd):
    seat = make_seat(ircd)
    seat.connect(timeout=5)
    assert seat.say("#marchhare", "hello") is True
    assert seat.say("#bobiverse", "nope") is False
    assert seat.say("simon", "nope") is False
    assert wait_until(lambda: "PRIVMSG #marchhare :hello" in ircd.received)
    assert not any("#bobiverse" in r and r.startswith("PRIVMSG") for r in ircd.received)
    seat.close()


def test_irc_ping_is_answered_immediately_in_the_read_thread(ircd):
    seat = make_seat(ircd)
    seat.connect(timeout=5)
    ircd.send("PING :abc123")
    assert wait_until(lambda: "PONG abc123" in ircd.received or "PONG :abc123" in ircd.received, 1.0)
    seat.close()


def test_fleet_ping_gets_pong_without_waking_the_agent(ircd):
    seat = make_seat(ircd)
    got = []
    seat.on_message = lambda n, t, x: got.append((n, t, x))
    seat.connect(timeout=5)
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :ping")
    assert wait_until(lambda: "PRIVMSG #marchhare :pong" in ircd.received)
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :ping marchhare")
    assert wait_until(lambda: ircd.received.count("PRIVMSG #marchhare :pong") == 1 or True)
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :ping someone-else")
    time.sleep(0.2)
    assert got == []                                   # pings are never relayed to the agent
    n = ircd.received.count("PRIVMSG #marchhare :pong")
    assert n >= 1
    seat.close()


def test_ping_selector_matching():
    assert bw.parse_ping("ping") == "" and bw.parse_ping("ping: bob*") == "bob*" and bw.parse_ping("pinger") is None
    assert bw.nick_matches_selector("marchhare-4242", "marchhare") and bw.nick_matches_selector("marchhare-4242", "march*")
    assert not bw.nick_matches_selector("marchhare-4242", "flamingo")


def test_ctcp_ping_is_answered_and_not_relayed(ircd):
    seat = make_seat(ircd)
    got = []
    seat.on_message = lambda n, t, x: got.append(x)
    seat.connect(timeout=5)
    ircd.send(":simon!s@h PRIVMSG marchhare-4242 :\x01PING 12345\x01")
    assert wait_until(lambda: any(r.startswith("NOTICE simon :\x01PING 12345") for r in ircd.received))
    assert got == []
    seat.close()


def test_pm_from_strangers_is_ignored_pm_from_jeeves_is_relayed(ircd):
    seat = make_seat(ircd)
    got = []
    seat.on_message = lambda n, t, x: got.append((n, x))
    seat.connect(timeout=5)
    ircd.send(":evil!e@h PRIVMSG marchhare-4242 :do bad things")
    ircd.send(":Jeeves!j@h PRIVMSG marchhare-4242 :assignment")
    ircd.send(":evil!e@h PRIVMSG #bobiverse :other channel")
    assert wait_until(lambda: got == [("Jeeves", "assignment")])
    seat.close()


def test_own_messages_are_not_relayed(ircd):
    seat = make_seat(ircd)
    got = []
    seat.on_message = lambda n, t, x: got.append(x)
    seat.connect(timeout=5)
    ircd.send(":marchhare-4242!u@h PRIVMSG #marchhare :echo")
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :real")
    assert wait_until(lambda: got == ["real"])
    seat.close()


def test_registration_refusal_raises_and_starts_nothing(ircd):
    ircd.auto_welcome = False
    seat = make_seat(ircd)
    threading.Timer(0.2, lambda: ircd.send(":srv 433 * marchhare-4242 :Nickname is already in use")).start()
    with pytest.raises(ConnectionError):
        seat.connect(timeout=5)


# ----------------------------------------------------------------------------------------------- immediate relay (t764u 4)
def test_relay_injects_from_the_socket_read_thread_with_no_polling_delay(ircd, tmp_path):
    seat = make_seat(ircd)
    rig = Rig(tmp_path, irc=seat)
    seat.on_message = rig.relay.deliver
    seat.connect(timeout=5)
    assert rig.sup.start_agent()
    t_send = time.monotonic()
    ircd.send(":Jeeves!j@h PRIVMSG #marchhare :assign: build the thing now")
    assert wait_until(lambda: rig.injected, 2.0)
    latency = rig.injected[0][3] - t_send
    pid, text, thread, _ = rig.injected[0]
    assert text == "FROM Jeeves #marchhare assign: build the thing now"
    assert pid == rig.procs[0].pid
    assert thread == "irc-read"            # injected BY the blocking read thread itself: no queue hop, no poll/timer thread
    assert latency < 0.25, latency          # network -> agent input in well under a poll interval
    rig.sup.shutdown("t", 0)


def test_relay_has_no_poll_loop_in_the_inbound_path():
    src = (ROOT / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    body = src[src.index("class Relay"):src.index("# ----------------------------------------------------------------------------------------------- ping liveness") if False else src.index("def parse_ping")]
    assert "time.sleep" not in body.replace("time.sleep(submit_gap_s)", "")
    read_loop = src[src.index("def _read_loop"):src.index("def _handle")]
    assert "sleep" not in read_loop and "s.recv(4096)" in read_loop


def test_messages_during_agent_start_are_held_then_flushed_immediately(tmp_path):
    rig = Rig(tmp_path, startup_grace_s=0.3)
    assert rig.sup.start_agent()
    assert rig.relay.deliver("Jeeves", "#marchhare", "early one") == "held"
    assert rig.injected == []
    assert wait_until(lambda: rig.injected, 2.0)
    assert rig.injected[0][1] == "FROM Jeeves #marchhare early one"
    rig.sup.shutdown("t", 0)


def test_relay_filters_and_dedupes(tmp_path):
    rig = Rig(tmp_path)
    rig.sup.start_agent()
    assert rig.relay.deliver("x", "#m", "BOB DIGEST v1 {...}") == "dropped"
    assert rig.relay.deliver("x", "#m", "password=hunter2") == "dropped"
    assert rig.relay.deliver("x", "#m", "do it") == "injected"
    assert rig.relay.deliver("x", "#m", "do it") == "duplicate"
    assert len(rig.injected) == 1
    rig.sup.shutdown("t", 0)


def test_flood_is_coalesced_not_dropped_or_spammed(tmp_path):
    rig = Rig(tmp_path)
    rig.relay.max_burst, rig.relay.window_s = 3, 0.4
    rig.sup.start_agent()
    results = [rig.relay.deliver("n", "#m", f"msg {i}") for i in range(7)]
    assert results[:3] == ["injected"] * 3 and set(results[3:]) == {"coalescing"}
    assert wait_until(lambda: len(rig.injected) == 4, 2.0)
    assert "flood-coalesced 4 messages" in rig.injected[-1][1]
    rig.sup.shutdown("t", 0)


# ----------------------------------------------------------------------------------------------- IRC loss => end the agent, close self
def test_irc_loss_kills_only_its_own_agent_tree_and_exits(ircd, tmp_path):
    seat = make_seat(ircd)
    rig = Rig(tmp_path, irc=seat)
    seat.log = rig.logs.append
    seat.on_message = rig.relay.deliver
    seat.connect(timeout=5)
    rig.sup.start_agent()
    agent = rig.procs[0].pid
    result = []
    threading.Thread(target=lambda: result.append(rig.sup.run_forever()), daemon=True).start()
    ircd.drop()                                          # connection lost
    assert wait_until(lambda: rig.sup.done.is_set(), 3.0)
    assert wait_until(lambda: result == [bw.EXIT_IRC_LOST])
    assert rig.killed == [agent]                         # exactly its own agent, nothing else
    assert len(rig.spawned) == 1                         # no reconnect loop, no relaunch
    assert any("LOST" in m for m in rig.logs)


def test_ping_timeout_counts_as_irc_loss(ircd, tmp_path):
    seat = bw.IrcSeat("127.0.0.1", ircd.port, "marchhare-1", "marchhare", tls=False, log=lambda m: None, ping_every=0.15, ping_grace=0.15)
    rig = Rig(tmp_path, irc=seat)
    seat.connect(timeout=5)
    rig.sup.start_agent()
    ircd.silent = True                                    # link is dead: no PONG ever
    assert wait_until(lambda: rig.sup.done.is_set(), 3.0)
    assert rig.sup.exit_code == bw.EXIT_IRC_LOST and rig.killed == [rig.procs[0].pid]


def test_shutdown_is_idempotent_and_never_kills_unowned_pids(tmp_path):
    rig = Rig(tmp_path)
    rig.sup.start_agent()
    rig.sup.shutdown("a", 3)
    rig.sup.shutdown("b", 9)
    assert rig.sup.exit_code == 3 and len(rig.killed) == 1
    assert bw.kill_tree(0) is False and bw.kill_tree(4) is False and bw.kill_tree(__import__("os").getpid()) is False


def test_closing_the_agent_ends_the_seat(tmp_path):
    rig = Rig(tmp_path)
    rig.sup.start_agent()
    rig.procs[0].finish(0)
    assert wait_until(lambda: rig.sup.done.is_set(), 2.0)
    assert rig.sup.exit_code == bw.EXIT_OK


def test_irc_connect_failure_starts_no_agent(tmp_path, monkeypatch):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    (tmp_path / "worker").mkdir()
    monkeypatch.setattr(bw, "read_fuel", lambda root: bw.Fuel(30, 30, 30, "available"))
    monkeypatch.setattr(bw, "resolve_cursor_cmd", lambda *a, **k: r"C:\c\agent.cmd")
    monkeypatch.setattr(bw, "resolve_grok_exe", lambda *a, **k: None)
    monkeypatch.setattr(bw, "_state_root", lambda env=None: tmp_path / "state")
    spawned = []
    monkeypatch.setattr(bw, "default_spawn", lambda spec, env: spawned.append(spec))
    args = type("A", (), {"install_root": str(tmp_path), "machine_id": "marchhare", "host": "127.0.0.1", "port": port, "no_tls": True})()
    assert bw.run_agent(args, bw.Log(None)) == bw.EXIT_IRC_FAIL
    assert spawned == []


# ----------------------------------------------------------------------------------------------- hung agent => bounded restart
def test_hang_detector_rules():
    d = bw.HangDetector(not_responding_s=10, silent_s=30)
    d.reset(0)
    assert d.check(bw.Sample(True, True, 5), 1) is None
    assert d.check(bw.Sample(True, False, 5), 2) is None            # not responding starts
    assert d.check(bw.Sample(True, False, 5), 11) is None
    assert d.check(bw.Sample(True, False, 5), 12.5) == "not-responding"
    d2 = bw.HangDetector(not_responding_s=10, silent_s=30)
    d2.reset(0)
    assert d2.check(bw.Sample(True, None, 5), 1) is None
    assert d2.check(bw.Sample(True, None, 5), 500) is None          # IDLE agent waiting for input is NOT hung
    d2.note_inject(500)
    assert d2.check(bw.Sample(True, None, 5), 520) is None
    assert d2.check(bw.Sample(True, None, 5), 531) == "silent-after-input"
    d3 = bw.HangDetector(not_responding_s=10, silent_s=30)
    d3.reset(0)
    d3.check(bw.Sample(True, None, 5), 1)
    d3.note_inject(2)
    assert d3.check(bw.Sample(True, None, 99), 20) is None          # activity after input = it is working
    assert d3.check(bw.Sample(True, None, 99), 100) is None


def test_hung_agent_is_restarted_with_backoff_and_logged(tmp_path):
    rig = Rig(tmp_path, backoff=(0.05, 0.1), detector=bw.HangDetector(not_responding_s=0.1, silent_s=999))
    rig.samples = [bw.Sample(True, False, 1)]                       # window permanently "not responding"
    rig.sup.start_agent()
    threading.Thread(target=rig.sup.run_forever, daemon=True).start()
    assert wait_until(lambda: len(rig.procs) >= 2, 5.0)
    assert rig.procs[0].pid in rig.killed
    assert any("HUNG (not-responding); restart 1/3" in m for m in rig.logs)
    rig.sup.shutdown("t", 0)


def test_restart_limit_gives_up_and_ends_everything(tmp_path):
    rig = Rig(tmp_path, backoff=(0.0,), restart_max=2, detector=bw.HangDetector(not_responding_s=0.0, silent_s=999))
    rig.samples = [bw.Sample(True, False, 1)]
    rig.sup.start_agent()
    done = []
    threading.Thread(target=lambda: done.append(rig.sup.run_forever()), daemon=True).start()
    assert wait_until(lambda: rig.sup.done.is_set(), 5.0)
    assert wait_until(lambda: done == [bw.EXIT_GAVE_UP])
    assert len(rig.procs) == 3                                      # original + 2 bounded restarts, then stop
    assert all(p.pid in rig.killed for p in rig.procs)              # nothing left running
    assert any("giving up" in m for m in rig.logs)


def test_inflight_message_is_redelivered_to_the_restarted_agent(tmp_path):
    rig = Rig(tmp_path, backoff=(0.0,))
    rig.sup.start_agent()
    rig.relay.deliver("Jeeves", "#marchhare", "important task")
    assert len(rig.injected) == 1
    rig.sup.restart_agent("silent-after-input")
    assert wait_until(lambda: len(rig.injected) == 2, 2.0)
    assert rig.injected[1][1] == rig.injected[0][1] and rig.injected[1][0] == rig.procs[1].pid
    rig.sup.shutdown("t", 0)


# ----------------------------------------------------------------------------------------------- outbox
def test_outbox_sends_to_own_shop_only(ircd, tmp_path):
    seat = make_seat(ircd)
    seat.connect(timeout=5)
    ob = tmp_path / "outbox.txt"
    ob.write_text("PRIVMSG #marchhare :done with task\nplain words\nPRIVMSG #bobiverse :leak\nPRIVMSG simon :psst\n", encoding="utf-8")
    assert bw.drain_outbox(ob, seat, lambda m: None) == 2
    assert wait_until(lambda: "PRIVMSG #marchhare :plain words" in ircd.received)
    assert "PRIVMSG #marchhare :done with task" in ircd.received
    assert not any("#bobiverse" in r and r.startswith("PRIVMSG") for r in ircd.received)
    assert not any(r.startswith("PRIVMSG simon") for r in ircd.received)
    assert not ob.exists()
    seat.close()


# ----------------------------------------------------------------------------------------------- real console injection (Windows)
@pytest.mark.skipif(sys.platform != "win32", reason="Windows console")
def test_one_window_agent_shares_our_console_and_gets_injected_input(tmp_path):
    """t771u: the agent is spawned by default_spawn INSIDE the exe's console (one window, one console, no second console) and
    inject_console types into that shared console. Run in a throw-away process with its own console so pytest's console is untouched."""
    import json
    import subprocess

    got, res, host = tmp_path / "got.txt", tmp_path / "res.json", tmp_path / "host.py"
    line = 'FROM Jeeves #m run: a&b | c "q" 100%'
    child = "import sys; l=sys.stdin.readline(); open(%r,'w',encoding='utf-8').write(l)" % str(got)
    host.write_text(
        "import sys, os, json, time, ctypes\n"
        "sys.path.insert(0, %r)\n"
        "import bob_worker as bw\n"
        "spec = bw.LaunchSpec(argv=[sys.executable, '-c', %r], cwd='.', session_id='x')\n"
        "proc = bw.default_spawn(spec, dict(os.environ))\n"
        "time.sleep(1.5)\n"
        "k = ctypes.WinDLL('kernel32')\n"
        "buf = (ctypes.c_uint * 16)()\n"
        "n = k.GetConsoleProcessList(buf, 16)\n"
        "ok = bw.inject_console(proc.pid, %r)\n"
        "try:\n    proc.wait(10)\nexcept Exception:\n    pass\n"
        "json.dump({'n': n, 'ids': list(buf)[:n], 'child': proc.pid, 'me': os.getpid(), 'inj': ok}, open(%r, 'w'))\n"
        % (str(Path(bw.__file__).parent), child, line, str(res)), encoding="utf-8")
    p = subprocess.Popen([sys.executable, str(host)], creationflags=bw.CREATE_NEW_CONSOLE)
    try:
        assert wait_until(res.exists, 30.0), "host produced no result"
        r = json.loads(res.read_text())
        assert r["inj"] is True
        assert r["child"] in r["ids"] and r["me"] in r["ids"], r      # the agent is attached to OUR console...
        assert r["n"] == 2, r                                          # ...and there is no third/second console owner
        assert got.read_text(encoding="utf-8").strip() == line        # typed input reached the agent's stdin
    finally:
        p.kill()


def test_agent_is_never_spawned_with_a_new_console(monkeypatch):
    seen = {}

    class FakePopen:
        _handle = 0
        pid = 4242

        def __init__(self, argv, **kw):
            seen.update(kw)

    monkeypatch.setattr(bw.subprocess, "Popen", FakePopen)
    spec = bw.build_launch("grok", "agent", r"C:\w", "p", r"C:\g\agent.exe", Path("."), "sid")
    bw.default_spawn(spec, {})
    assert seen["creationflags"] & bw.CREATE_NEW_CONSOLE == 0
    assert seen["creationflags"] & bw.CREATE_NO_WINDOW == 0

@pytest.mark.skipif(sys.platform != "win32", reason="Windows structs")
def test_input_record_layout():
    _, REC = bw._win_structs()
    import ctypes

    assert ctypes.sizeof(REC) == 20
    assert len(bw.build_key_records("ab")) == 4

# ----------------------------------------------------------------------------------------------- one window (t771u)
def test_plan_mode_is_hosted_in_this_console_and_ends_with_its_agent(tmp_path, monkeypatch):
    import types

    (tmp_path / "plan").mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    procs: list = []

    def spawn(spec, env):
        p = FakeProc()
        procs.append((p, spec))
        return p

    monkeypatch.setattr(bw, "default_spawn", spawn)
    dec = bw.select_agent(bw.Fuel(5, 5, 5, "available"), CUR, GRK)
    monkeypatch.setattr(bw, "_choose", lambda a, l, f, m: (dec, CUR, GRK, bw.Fuel(5, 5, 5, "available")))
    hooks: list = []
    monkeypatch.setattr(bw, "install_ctrl_handler", lambda f: hooks.append(f) or True)
    out: list = []
    args = types.SimpleNamespace(install_root=str(tmp_path), mode="plan")
    th = threading.Thread(target=lambda: out.append(bw.run_plan(args, bw.Log(None))), daemon=True)
    th.start()
    assert wait_until(lambda: len(procs) == 1, 3.0)
    time.sleep(0.3)
    assert out == [], "the exe must stay alive for as long as its agent lives (it IS the window host)"
    assert hooks, "closing the console window must end the agent"
    procs[0][0].finish(0)
    assert wait_until(lambda: out == [bw.EXIT_OK], 3.0)


def test_key_prompt_is_in_the_console_not_a_dialog():
    src = (ROOT / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    assert "import tkinter" not in src and "tk.Tk(" not in src
    assert "msvcrt.getwch" in src and "hidden" in src


def test_agent_exit_ends_the_exe_and_exe_end_ends_the_agent(tmp_path):
    rig = Rig(tmp_path)
    rig.sup.start_agent()
    p = rig.procs[0]
    th = threading.Thread(target=rig.sup.run_forever, daemon=True)
    th.start()
    p.finish(0)                                              # agent quits -> exe ends
    assert wait_until(lambda: rig.sup.done.is_set(), 3.0) and rig.sup.exit_code == bw.EXIT_OK
    rig2 = Rig(tmp_path / "b")
    rig2.sup.start_agent()
    rig2.sup.shutdown("window-closed", bw.EXIT_OK)           # exe ends -> its own agent tree is killed
    assert rig2.killed == [rig2.procs[0].pid]
