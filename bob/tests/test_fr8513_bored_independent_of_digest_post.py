"""FR #8513: DONE -> !bored must not wait on worker digest POST success."""
from __future__ import annotations

import inspect
from pathlib import Path

import bob_worker as bw


def test_digest_post_failure_writes_marker_and_unhealthy_flag(monkeypatch, tmp_path: Path):
    calls: list[dict] = []

    def _fail_post(url, payload, **kw):
        calls.append(dict(payload))
        return False

    monkeypatch.setattr(bw, "_http_post_json", _fail_post)
    env = {
        "BOB_WORKER_RUN_DIR": str(tmp_path),
        "BOB_REPORT_URL": "https://example.invalid/bob/v1/report",
    }
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=9192,
        nick="redqueen-9192",
        kind="grok",
        env=env,
        sleep=lambda _s: None,
    )
    assert ok is False
    assert calls, "digest POST was attempted"
    assert any(c.get("digest_post_failed") for c in calls)
    marker = tmp_path / "digest-post-fail.json"
    assert marker.is_file()
    assert "digest_post_failed" in marker.read_text(encoding="utf-8")


def test_bored_emitter_does_not_call_digest_http():
    """FR #8513: !bored / on_outbox paths must not POST digest (URLError cannot block idle)."""
    on_outbox_src = inspect.getsource(bw.BoredEmitter.on_outbox)
    post_bored_src = inspect.getsource(bw.Supervisor.post_bored)
    assert "post_digest" not in on_outbox_src
    assert "_http_post_json" not in on_outbox_src
    assert "post_digest" not in post_bored_src
    assert "_http_post_json" not in post_bored_src
    # Existing DONE -> !bored timing coverage stays in test_bob_worker_bored_020.


def test_successful_digest_post_clears_fail_marker(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bw, "_http_post_json", lambda *a, **k: True)
    env = {
        "BOB_WORKER_RUN_DIR": str(tmp_path),
        "BOB_REPORT_URL": "https://example.invalid/bob/v1/report",
    }
    marker = tmp_path / "digest-post-fail.json"
    marker.write_text('{"digest_post_failed": true}', encoding="utf-8")
    ok = bw.post_digest_seat_kind(
        machine="redqueen",
        pid=9192,
        nick="redqueen-9192",
        kind="grok",
        env=env,
        sleep=lambda _s: None,
    )
    assert ok is True
    assert not marker.is_file()
