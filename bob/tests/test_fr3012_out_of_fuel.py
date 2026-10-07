"""FR #3012: agent 402 / usage-exhausted is out-of-fuel, not done-miss.

Detect mid-job fuel exhaustion, GIVEUP the open ACK immediately, suppress !bored
until fuel returns, and avoid the done-miss / wait(0) spin path.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import bob_worker as bw
from test_fr2802_bored_on_turn_end import FakeClock, _emitter, _wait


def test_is_out_of_fuel_text_detects_402_payment_required():
    assert bw.is_out_of_fuel_text(
        "402 Payment Required: Grok Build usage balance exhausted"
    )
    assert bw.is_out_of_fuel_text(
        'error: {"message":"Payment Required: usage balance exhausted","status":402}'
    )
    assert bw.is_out_of_fuel_text("Grok Build usage balance exhausted")
    assert bw.is_out_of_fuel_text("provider out of credits mid-turn")


def test_is_out_of_fuel_text_ignores_token_count_402():
    # Bare "402" in completion_tokens / timestamps must not trip out-of-fuel.
    line = (
        '{"ts":"2026-10-07T02:25:30.161Z","msg":"shell.turn.inference_done",'
        '"ctx":{"completion_tokens":402,"prompt_tokens":101459}}'
    )
    assert not bw.is_out_of_fuel_text(line)
    assert not bw.is_out_of_fuel_text("")
    assert not bw.is_out_of_fuel_text("relay: injected FROM Jeeves #m FR o/r#1")


def test_out_of_fuel_giveup_line():
    assert bw.out_of_fuel_giveup_line("MRB o/r#2995") == "GIVEUP MRB o/r#2995 out-of-fuel"
    assert "out-of-fuel" in bw.out_of_fuel_giveup_line("")


def test_note_out_of_fuel_giveups_open_ack_and_suppresses_bored():
    clock = FakeClock(0.0)
    released: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=5.0, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.on_outbox("ACK MRB o/r#2995")
    clock.advance(2.0)
    n0 = len(sent)
    e.note_out_of_fuel("402 Payment Required: Grok Build usage balance exhausted")
    assert e.out_of_fuel is True
    assert e.ack_open is False
    assert released == ["GIVEUP MRB o/r#2995 out-of-fuel"]
    assert any("out-of-fuel" in m for m in logs)
    # Idle long enough that a normal seat would !bored — must stay quiet.
    clock.advance(30.0)
    time.sleep(0.05)
    assert not any(r in ("idle", "nak", "done-miss", "free", "done") for _, r in e.sent[n0:])
    # Fuel returns → !bored may resume.
    e.clear_out_of_fuel()
    assert e.out_of_fuel is False
    clock.advance(6.0)
    assert _wait(lambda: any(r == "idle" for _, r in e.sent[n0:]), clock, timeout=3.0), e.sent[n0:]
    e.stop()


def test_out_of_fuel_cancels_done_miss_and_sets_release_gen():
    clock = FakeClock(0.0)
    reminds: list[str] = []
    e, sent, logs = _emitter(clock, harvest_hold_s=90.0, done_miss_grace_s=20.0)
    e.done_miss_remind_fn = lambda key: reminds.append(key)
    e.out_of_fuel_release_fn = lambda key: None
    e.on_outbox("ACK MRB o/r#2994")
    e.turn_started(at=clock())
    clock.advance(1.0)
    e.turn_ended(at=clock())
    assert any("done-miss armed" in m for m in logs)
    e.note_out_of_fuel("402 Payment Required: Grok Build usage balance exhausted")
    clock.advance(30.0)
    time.sleep(0.05)
    assert reminds == []
    assert e._release_gen == e._turn_gen
    assert not any(r == "done-miss" for _, r in e.sent)
    e.stop()


def test_out_of_fuel_watcher_fake_agent_402_mid_job(tmp_path: Path):
    """Fake agent writes a 402 line to a log; watcher fires while ACK is open."""
    clock = FakeClock(0.0)
    log_path = tmp_path / "unified.jsonl"
    log_path.write_text("", encoding="utf-8")
    released: list[str] = []
    e, sent, logs = _emitter(clock, idle_s=120.0, repeat_s=180.0)
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.on_outbox("ACK MRB SimonBarnett/bobiverse#2995")
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
        # Wait until the watcher has opened the empty log (EOF offset), then append.
        assert _wait(
            lambda: any("watcher following" in m for m in logs),
            clock,
            timeout=2.0,
        ), logs
        time.sleep(0.15)
        # Mid-job: agent emits 402 (fake).
        line = (
            '{"ts":"2026-10-07T02:12:42Z","lvl":"error","msg":'
            '"402 Payment Required: Grok Build usage balance exhausted"}\n'
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
        assert _wait(lambda: len(hits) >= 1, clock, timeout=3.0), (hits, logs)
        assert released == [
            "GIVEUP MRB SimonBarnett/bobiverse#2995 out-of-fuel"
        ]
        assert e.out_of_fuel is True
        assert e.ack_open is False
        n0 = len(sent)
        clock.advance(200.0)
        time.sleep(0.05)
        assert not any(r in ("idle", "nak", "done-miss") for _, r in e.sent[n0:])
    finally:
        stop.set()
        th.join(timeout=2.0)
        e.stop()


def test_post_digest_out_of_fuel_posts_json(tmp_path: Path, monkeypatch):
    posted: list[tuple[str, dict]] = []

    def fake_post(url: str, payload: dict, timeout: float = 10.0) -> bool:
        posted.append((url, dict(payload)))
        return True

    monkeypatch.setattr(bw, "_http_post_json", fake_post)
    monkeypatch.setenv("BOB_REPORT_URL", "https://example.test/bob/v1/report")
    ok = bw.post_digest_out_of_fuel(
        machine="marchhare",
        nick="marchhare-7720",
        evidence="402 Payment Required: Grok Build usage balance exhausted",
    )
    assert ok is True
    assert len(posted) == 1
    url, body = posted[0]
    assert url.endswith("/bob/v1/report")
    assert body.get("id") == "marchhare"
    assert body.get("status") == "out_of_fuel"
    assert "out-of-fuel" in str(body.get("working_on") or "").lower()
    assert body.get("out_of_tokens") is True


def test_skill_fr3012_contiguous():
    skill = Path(__file__).resolve().parents[1] / ".grok/skills/bobiverse-bob-worker/SKILL.md"
    raw = skill.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "FR #3012" in t
    assert "out-of-fuel" in t.lower() or "out of fuel" in t.lower()
    assert "402" in t
    assert "GIVEUP" in t
