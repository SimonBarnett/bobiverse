"""FR #8814: fuel exhausted → dialog + quit (no out_of_fuel digest zombie)."""
from __future__ import annotations

import bob_worker as bw


def test_fr8814_out_of_fuel_quit_enabled_default():
    assert bw.out_of_fuel_quit_enabled({}) is True
    assert bw.out_of_fuel_quit_enabled({"BOB_WORKER_OUT_OF_FUEL_QUIT": "1"}) is True
    assert bw.out_of_fuel_quit_enabled({"BOB_WORKER_OUT_OF_FUEL_QUIT": "0"}) is False
    assert bw.out_of_fuel_quit_enabled({"BOB_WORKER_OUT_OF_FUEL_QUIT": "false"}) is False


def test_fr8814_format_dialog_includes_pool_and_quit_note():
    text = bw.format_out_of_fuel_dialog_text(
        pool="opencode_free",
        remaining="free=0 go=0",
        reset_hint="week reset Mon",
        evidence="fuel-exhausted:opencode-free",
        nick="redqueen-12012",
    )
    assert "opencode_free" in text
    assert "free=0" in text
    assert "week reset" in text
    assert "redqueen-12012" in text
    assert "leave the digest" in text.lower() or "closes" in text.lower() or "close" in text.lower()


def test_fr8814_show_dialog_uses_show_fn():
    seen: list[tuple[str, str]] = []

    def _show(text: str, title: str) -> None:
        seen.append((text, title))

    ok = bw.show_out_of_fuel_dialog(
        pool="opencode",
        remaining="0",
        evidence="out-of-fuel",
        nick="m-1",
        show_fn=_show,
        env={"BOB_WORKER_FUEL_DIALOG": "1"},
    )
    assert ok is True
    assert len(seen) == 1
    assert "m-1" in seen[0][0]
    assert "Bobiverse" in seen[0][1]


def test_fr8814_show_dialog_skipped_when_disabled():
    logs: list[str] = []
    ok = bw.show_out_of_fuel_dialog(
        pool="opencode",
        show_fn=None,
        env={"BOB_WORKER_FUEL_DIALOG": "0"},
        log=logs.append,
    )
    assert ok is False
    assert any("dialog skipped" in m for m in logs)


def test_fr8814_note_out_of_fuel_invokes_quit_fn(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_OUT_OF_FUEL_QUIT", "1")
    clock = bw.FakeClock(0.0) if hasattr(bw, "FakeClock") else None
    # Use the same helper pattern as test_fr3012 when FakeClock lives in the test module.
    from test_fr3012_out_of_fuel import FakeClock, _emitter

    clock = FakeClock(0.0)
    released: list[str] = []
    quit_ev: list[str] = []
    e, _sent, logs = _emitter(clock, harvest_hold_s=5.0, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_release_fn = lambda key: released.append(bw.out_of_fuel_giveup_line(key))
    e.out_of_fuel_quit_fn = lambda ev: quit_ev.append(ev or "")
    e.on_outbox("ACK FR o/r#8814")
    clock.advance(1.0)
    e.note_out_of_fuel("fuel-exhausted:opencode-free Free usage limit reached")
    assert released == ["GIVEUP FR o/r#8814 out-of-fuel"]
    assert quit_ev and "fuel-exhausted:opencode-free" in quit_ev[0]
    assert any("quitting seat" in m for m in logs)
    e.stop()


def test_fr8814_note_out_of_fuel_skips_quit_when_disabled(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_OUT_OF_FUEL_QUIT", "0")
    from test_fr3012_out_of_fuel import FakeClock, _emitter

    clock = FakeClock(0.0)
    quit_ev: list[str] = []
    e, _sent, logs = _emitter(clock, harvest_hold_s=5.0, idle_s=5.0, repeat_s=5.0)
    e.out_of_fuel_release_fn = lambda key: None
    e.out_of_fuel_quit_fn = lambda ev: quit_ev.append(ev or "")
    e.on_outbox("ACK FR o/r#1")
    e.note_out_of_fuel("402 Payment Required")
    assert quit_ev == []
    assert any("holding seat" in m for m in logs)
    e.stop()


def test_fr8814_post_digest_worker_remove_posts_op(monkeypatch):
    posted: list[dict] = []

    def _fake_post(url, payload, log=None):
        posted.append(dict(payload))
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    ok = bw.post_digest_worker_remove(
        machine="redqueen",
        nick="redqueen-12012",
        pid=12012,
        url="https://example.test/bob/v1/report",
        env={},
    )
    assert ok is True
    assert posted and posted[0].get("op") == "worker-remove"
    assert posted[0].get("nick") == "redqueen-12012"
    assert posted[0].get("pid") == 12012


def test_fr8814_exit_code_defined():
    assert bw.EXIT_OUT_OF_FUEL == 10
