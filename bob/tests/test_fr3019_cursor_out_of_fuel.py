"""FR #3019: Cursor (non-grok) out-of-fuel parity with FR #3012."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_is_out_of_fuel_text_cursor_needs_auth_and_out_of_tokens():
    assert bw.is_out_of_fuel_text("OUTCOME_NEEDS_AUTH: cannot charge on-demand")
    assert bw.is_out_of_fuel_text("agent NEEDS_AUTH — unpaid invoice")
    assert bw.is_out_of_fuel_text("cursor: out of tokens remaining")
    assert bw.is_out_of_fuel_text("rate limited by provider")
    assert not bw.is_out_of_fuel_text('{"completion_tokens":402}')


def test_should_start_fuel_watcher_cursor_and_grok():
    assert bw.should_start_fuel_watcher("grok") is True
    assert bw.should_start_fuel_watcher("cursor") is True
    assert bw.should_start_fuel_watcher("dialog") is False
    assert bw.should_start_fuel_watcher("plan") is False


def test_default_out_of_fuel_log_path_by_kind(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_WORKER_OUT_OF_FUEL_LOG", raising=False)
    assert bw.default_out_of_fuel_log_path("grok") is not None
    assert bw.default_out_of_fuel_log_path("cursor") is None
    override = tmp_path / "cursor-fuel.log"
    monkeypatch.setenv("BOB_WORKER_OUT_OF_FUEL_LOG", str(override))
    assert bw.default_out_of_fuel_log_path("cursor") == override
    assert bw.default_out_of_fuel_log_path("grok") == override


def test_start_fuel_watcher_does_not_early_return_for_cursor():
    text = Path(__file__).resolve().parents[1].joinpath("scripts/bob_worker.py").read_text(
        encoding="utf-8"
    )
    i = text.index("def _start_fuel_watcher")
    window = text[i : i + 1200]
    assert "should_start_fuel_watcher" in window
    assert '!= "grok"' not in window
    assert "#3019" in window
    assert "cursor" in window.lower()


def test_cursor_log_watcher_giveup_on_needs_auth(tmp_path: Path):
    clock = FakeClock(0.0)
    log_path = tmp_path / "cursor-agent.log"
    log_path.write_text("", encoding="utf-8")
    released: list[str] = []
    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.on_outbox("ACK FR SimonBarnett/bobiverse#3019")
    clock.advance(1.0)

    stop = threading.Event()
    hits: list[str] = []

    def on_hit(text: str) -> None:
        hits.append(text)
        e.note_out_of_fuel(text)

    watcher = bw.GrokOutOfFuelWatcher(
        log_path_fn=lambda: log_path,
        on_hit=on_hit,
        stop_event=stop,
        poll_s=0.05,
        log=logs.append,
    )
    th = threading.Thread(target=watcher.run, daemon=True)
    th.start()
    try:
        assert _wait(lambda: any("watcher following" in m for m in logs), clock, timeout=2.0), logs
        time.sleep(0.15)
        with log_path.open("a", encoding="utf-8") as f:
            f.write("error: NEEDS_AUTH unpaid invoice — cannot continue\n")
            f.flush()
        assert _wait(lambda: len(hits) >= 1, clock, timeout=3.0), (hits, logs)
        assert released == ["GIVEUP FR SimonBarnett/bobiverse#3019 out-of-fuel"]
        assert e.out_of_fuel is True
        assert e.ack_open is False
    finally:
        stop.set()
        th.join(timeout=2.0)
        e.stop()


def test_mid_job_fuel_lost_poll_giveup_for_cursor_seat():
    """Cursor has no unified.jsonl — fuel-reading poll while ACK open must GIVEUP."""
    clock = FakeClock(0.0)
    released: list[str] = []
    lost_calls = {"n": 0}

    def fuel_lost() -> bool:
        lost_calls["n"] += 1
        return lost_calls["n"] >= 2  # first poll arm, second reports lost

    e, sent, logs = _emitter(clock, idle_s=120.0)
    e.fuel_poll_s = 5.0
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.fuel_lost_check_fn = fuel_lost
    e.on_outbox("ACK MRB o/r#99")
    clock.advance(1.0)
    # First due wake (~fuel_poll_s): records check time, lost=False.
    clock.advance(5.5)
    time.sleep(0.05)
    assert released == []
    # Second wake: fuel_lost True → GIVEUP.
    clock.advance(5.5)
    assert _wait(lambda: len(released) == 1, clock, timeout=3.0), (released, logs, lost_calls)
    assert released == ["GIVEUP MRB o/r#99 out-of-fuel"]
    assert e.out_of_fuel is True
    assert any("mid-job fuel reading exhausted" in m for m in logs)
    n0 = len(sent)
    clock.advance(60.0)
    time.sleep(0.05)
    assert not any(r in ("idle", "nak", "done-miss") for _, r in e.sent[n0:])
    e.stop()


def test_skill_fr3019_contiguous():
    skill = Path(__file__).resolve().parents[1] / ".grok/skills/bobiverse-bob-worker/SKILL.md"
    raw = skill.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "FR #3019" in t
    assert "cursor" in t.lower()
    assert "NEEDS_AUTH" in t or "fuel-reading poll" in t or "out-of-fuel" in t.lower()
