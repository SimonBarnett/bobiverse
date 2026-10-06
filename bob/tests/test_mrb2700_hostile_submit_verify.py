"""MRB #2700 hostile: FR #2696 submit-verify Enter-only edges."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
from test_fr2696_inject_submit_verify import FakeClock, FakeDropEnterTui


def test_mrb2700_max_retries_zero_never_sends_retry_enter():
    fake = FakeDropEnterTui(drop_enters=2)
    clock = FakeClock()
    ok = bw.inject_with_submit_verify(
        1, "FROM line",
        inject_fn=fake.inject, enter_fn=fake.enter_only, probe_fn=fake.probe,
        clock=clock, sleep=clock.sleep, log=fake.log,
        verify_s=1.0, max_retries=0, backoffs=(3.0, 5.0, 8.0), sync=True,
    )
    assert ok is True
    assert fake.enter_events == 2
    assert fake.submitted == []
    assert any("submit-verify FAILED" in m for m in fake.logs)
    assert not any("submit-verify retry=" in m for m in fake.logs)


def test_mrb2700_cursor_probe_is_none_skips_enter_retries(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY", "1")
    assert bw.make_submit_probe("cursor", cwd="C:\\x", session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", agent_pid=1) is None
    fake = FakeDropEnterTui(drop_enters=2)
    clock = FakeClock()
    enters = {"n": 0}

    def enter_spy(pid: int = 0) -> bool:
        enters["n"] += 1
        return fake.enter_only(pid)

    ok = bw.inject_with_submit_verify(
        1, "FROM line",
        inject_fn=fake.inject, enter_fn=enter_spy, probe_fn=None,
        clock=clock, sleep=clock.sleep, log=fake.log, sync=True,
    )
    assert ok is True
    assert enters["n"] == 0  # inject_fn owns the initial Enters; verify must not retry
    assert any("submit-verify skipped (no probe)" in m for m in fake.logs)


def test_mrb2700_verify_disabled_skips_loop(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY", "0")
    fake = FakeDropEnterTui(drop_enters=2)
    clock = FakeClock()
    retry_enters = {"n": 0}

    def enter_spy(pid: int = 0) -> bool:
        retry_enters["n"] += 1
        return True

    ok = bw.inject_with_submit_verify(
        1, "FROM line",
        inject_fn=fake.inject, enter_fn=enter_spy, probe_fn=lambda: False,
        clock=clock, sleep=clock.sleep, log=fake.log, sync=True,
    )
    assert ok is True
    assert retry_enters["n"] == 0
    assert not any("submit-verify" in m for m in fake.logs)


def test_mrb2700_never_repaste_when_all_retries_exhausted():
    fake = FakeDropEnterTui(drop_enters=50)
    clock = FakeClock()
    ok = bw.inject_with_submit_verify(
        1, "FROM once",
        inject_fn=fake.inject, enter_fn=fake.enter_only, probe_fn=fake.probe,
        clock=clock, sleep=clock.sleep, log=fake.log,
        verify_s=0.5, max_retries=3, backoffs=(0.5, 0.5, 0.5), sync=True,
    )
    assert ok is True
    assert fake.pastes == ["FROM once"]
    assert fake.submitted == []
    assert fake.enter_events == 2 + 3  # double Enter + 3 retries
    assert any("FAILED" in m for m in fake.logs)


def test_mrb2700_unified_probe_matches_pid_and_ts(tmp_path):
    log = tmp_path / "unified.jsonl"
    rows = [
        {"ts": "2026-10-06T12:00:00.000Z", "msg": "prompt.enqueue", "subsystem": "grok-pager", "pid": 111},
        {"ts": "2026-10-06T12:00:10.000Z", "msg": "prompt.enqueue", "subsystem": "grok-pager", "pid": 222},
        {"ts": "2026-10-06T12:00:10.000Z", "msg": "other", "subsystem": "grok-pager", "pid": 222},
    ]
    # probe filters on substring grok-pager in the raw line
    lines = []
    for r in rows:
        r2 = dict(r)
        # keep subsystem field; probe looks for "grok-pager" in line text
        lines.append(json.dumps(r2))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    import datetime as dt
    since = dt.datetime(2026, 10, 6, 12, 0, 5, tzinfo=dt.timezone.utc).timestamp()
    assert bw.probe_unified_prompt_enqueue(agent_pid=222, since_wall=since, log_path=log) is True
    assert bw.probe_unified_prompt_enqueue(agent_pid=111, since_wall=since, log_path=log) is False
    assert bw.probe_unified_prompt_enqueue(agent_pid=222, since_wall=since + 100, log_path=log) is False


def test_mrb2700_supervisor_inject_wiring_source():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    i = src.index("def _inject_line")
    body = src[i:i + 1200]
    assert "since_wall = time.time()" in body
    assert "clock=time.monotonic" in body
    assert "sync=False" in body
    assert "make_submit_probe" in body
    assert "send_console_enter" in body
    assert "inject_with_submit_verify" in body


def test_mrb2700_skill_submit_verify_bullet_contiguous():
    skill = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "**Submit verify (FR #2696)**" in text
    # Contiguous: never re-paste appears in the same bullet paragraph
    idx = text.index("**Submit verify (FR #2696)**")
    chunk = text[idx: idx + 500]
    assert "never re-paste" in chunk
    assert "BOB_WORKER_SUBMIT_VERIFY" in chunk


def test_mrb2700_backoff_env_garbage_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_VERIFY_BACKOFFS", "nope,,x")
    assert bw._submit_verify_backoffs() == (3.0, 5.0, 8.0)
