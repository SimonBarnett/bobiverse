"""FR #2696: after paste+Enter, verify TUI submit; retry Enter only (never re-paste)."""
from __future__ import annotations

import bob_worker as bw


class FakeDropEnterTui:
    """Fake inject target: paste once; drop the first K Enter events; then submit."""

    def __init__(self, drop_enters: int = 2):
        self.drop_remaining = int(drop_enters)
        self.pastes: list[str] = []
        self.enter_events = 0
        self.submitted: list[str] = []
        self._pending: str | None = None
        self.logs: list[str] = []

    def inject(self, pid: int, text: str, submit_gap_s: float | None = None) -> bool:
        self.pastes.append(text)
        self._pending = text
        # Mirror inject_console: two Enter writes after paste.
        self.enter_only(pid)
        self.enter_only(pid)
        return True

    def enter_only(self, pid: int = 0) -> bool:
        self.enter_events += 1
        if self.drop_remaining > 0:
            self.drop_remaining -= 1
            return True
        if self._pending is not None:
            self.submitted.append(self._pending)
            self._pending = None
        return True

    def probe(self) -> bool:
        return bool(self.submitted)

    def log(self, msg: str) -> None:
        self.logs.append(msg)


class FakeClock:
    def __init__(self, t0: float = 1000.0):
        self.t = float(t0)
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(float(s))
        self.t += float(s)


def test_submit_verify_env_defaults(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_SUBMIT_VERIFY_S", raising=False)
    monkeypatch.delenv("BOB_WORKER_SUBMIT_VERIFY_RETRIES", raising=False)
    monkeypatch.delenv("BOB_WORKER_SUBMIT_VERIFY", raising=False)
    assert bw._submit_verify_s() == 3.0
    assert bw._submit_verify_retries() == 3
    assert bw._submit_verify_enabled() is True
    assert bw._submit_verify_backoffs() == (3.0, 5.0, 8.0)


def test_submit_verify_env_override_and_disable(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY_S", "1.5")
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY_RETRIES", "2")
    assert bw._submit_verify_s() == 1.5
    assert bw._submit_verify_retries() == 2
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY", "0")
    assert bw._submit_verify_enabled() is False


def test_fr2696_drop_two_enters_retries_once_no_repaste():
    """K=2 matches first-inject race: initial double-Enter drops; retry Enter submits."""
    fake = FakeDropEnterTui(drop_enters=2)
    clock = FakeClock()
    ok = bw.inject_with_submit_verify(
        1,
        "FROM Jeeves #m nick: FR x/y#1 https://example/1",
        inject_fn=fake.inject,
        enter_fn=fake.enter_only,
        probe_fn=fake.probe,
        clock=clock,
        sleep=clock.sleep,
        log=fake.log,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        sync=True,
    )
    assert ok is True
    assert fake.pastes == ["FROM Jeeves #m nick: FR x/y#1 https://example/1"]
    assert len(fake.submitted) == 1
    assert fake.submitted[0] == fake.pastes[0]
    # 2 initial + 1 retry
    assert fake.enter_events == 3
    assert any("submit-verify retry=1" in m for m in fake.logs)
    assert any("submit-verify ok" in m for m in fake.logs)
    assert not any("FAILED" in m for m in fake.logs)


def test_fr2696_k0_no_retry_enter():
    fake = FakeDropEnterTui(drop_enters=0)
    clock = FakeClock()
    enters_before_verify = []

    def enter_spy(pid: int = 0) -> bool:
        # Count only verify-loop retries by wrapping after inject.
        return fake.enter_only(pid)

    # inject already consumes 2 enters internally; probe is True immediately.
    ok = bw.inject_with_submit_verify(
        1,
        "FROM line",
        inject_fn=fake.inject,
        enter_fn=enter_spy,
        probe_fn=fake.probe,
        clock=clock,
        sleep=clock.sleep,
        log=fake.log,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        sync=True,
    )
    assert ok is True
    assert len(fake.pastes) == 1
    assert len(fake.submitted) == 1
    assert fake.enter_events == 2  # only the inject_console double Enter
    assert not any("submit-verify retry=" in m for m in fake.logs)
    assert any("submit-verify ok" in m for m in fake.logs)


def test_fr2696_k_exceeds_retries_fails_ack_miss_still_arms():
    """K greater than initial Enters + max retries -> FAILED; inject still True so ack-miss arms."""
    fake = FakeDropEnterTui(drop_enters=20)
    clock = FakeClock()
    ok = bw.inject_with_submit_verify(
        1,
        "FROM assign",
        inject_fn=fake.inject,
        enter_fn=fake.enter_only,
        probe_fn=fake.probe,
        clock=clock,
        sleep=clock.sleep,
        log=fake.log,
        verify_s=1.0,
        max_retries=3,
        backoffs=(1.0, 1.0, 1.0),
        sync=True,
    )
    assert ok is True  # paste path succeeded; verify failure is logged, not a hard inject False
    assert len(fake.pastes) == 1
    assert fake.submitted == []
    assert any("submit-verify FAILED" in m for m in fake.logs)
    # ack-miss arming: Relay treats ok=True as injected (existing path).
    relay_logs: list[str] = []
    clock2 = FakeClock()
    relay = bw.Relay(log=relay_logs.append, clock=clock2, max_burst=8, window_s=30.0)
    fake2 = FakeDropEnterTui(drop_enters=20)
    relay.set_target(lambda line: bw.inject_with_submit_verify(
        1, line, inject_fn=fake2.inject, enter_fn=fake2.enter_only, probe_fn=fake2.probe,
        clock=clock2, sleep=clock2.sleep, log=relay_logs.append,
        verify_s=0.5, max_retries=1, backoffs=(0.5,), sync=True,
    ))
    status = relay.deliver("Jeeves", "#m", "marchhare-1: FR o/r#1 https://x/1")
    assert status == "injected"
    assert relay.injected == 1
    assert relay.last_unacked.startswith("FROM ")
    assert any("submit-verify FAILED" in m for m in relay_logs)


def test_fr2696_stop_fn_halts_retries():
    fake = FakeDropEnterTui(drop_enters=2)
    clock = FakeClock()
    stopped = {"n": 0}

    def stop() -> bool:
        # Become true after first wait window so we never retry Enter.
        stopped["n"] += 1
        return clock.t >= 1003.0

    ok = bw.inject_with_submit_verify(
        1,
        "FROM line",
        inject_fn=fake.inject,
        enter_fn=fake.enter_only,
        probe_fn=lambda: False,
        stop_fn=stop,
        clock=clock,
        sleep=clock.sleep,
        log=fake.log,
        verify_s=3.0,
        max_retries=3,
        backoffs=(3.0, 5.0, 8.0),
        sync=True,
    )
    assert ok is True
    assert fake.enter_events == 2  # no retry Enter
    assert any("submit-verify ok" in m or "submit-verify stop" in m for m in fake.logs)


def test_fr2696_send_console_enter_source_and_helpers():
    src = open(bw.__file__, encoding="utf-8").read()
    assert "def send_console_enter" in src
    assert "def inject_with_submit_verify" in src
    assert "def run_submit_verify_loop" in src
    assert "BOB_WORKER_SUBMIT_VERIFY_S" in src
    assert "submit-verify retry=" in src
    assert "FR #2696" in src


def test_fr2696_grok_probe_turn_started(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        '{"ts":"2026-10-06T12:00:00.000Z","type":"turn_started","turn_number":0}\n'
        '{"ts":"2026-10-06T12:00:05.000Z","type":"turn_started","turn_number":1}\n',
        encoding="utf-8",
    )
    # since just after turn 0
    import datetime as dt

    since = dt.datetime(2026, 10, 6, 12, 0, 2, tzinfo=dt.timezone.utc).timestamp()
    assert bw.probe_grok_session_submit(tmp_path, since_wall=since) is True
    since_late = dt.datetime(2026, 10, 6, 12, 0, 6, tzinfo=dt.timezone.utc).timestamp()
    assert bw.probe_grok_session_submit(tmp_path, since_wall=since_late) is False
