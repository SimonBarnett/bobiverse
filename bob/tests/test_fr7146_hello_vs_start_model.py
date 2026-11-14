"""FR #7146: hello model= stays configured; digest start_model is launch actual."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402


def test_fr7146_hello_configured_digest_start_model_is_actual(monkeypatch):
    """Both fields: shop hello keeps the configured id; digest start_model is actual."""
    captured: dict[str, Any] = {}

    def _fake_post(url: str, payload: dict, log=None):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    hello = bw.worker_hello_line("cursor", model="EXAMPLE_CONFIGURED", build="abc123def456")
    ok = bw.post_digest_seat_kind(
        machine="example",
        pid=1,
        nick="example-1",
        kind="cursor",
        model="EXAMPLE_ACTUAL",
        configured_model="EXAMPLE_CONFIGURED",
        model_mismatch=True,
        worker_build="abc123def456",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    assert hello == "worker ready kind=cursor model=EXAMPLE_CONFIGURED build=abc123def456"
    assert "EXAMPLE_ACTUAL" not in hello
    assert captured["payload"]["model"] == "EXAMPLE_ACTUAL"
    assert captured["payload"]["start_model"] == "EXAMPLE_ACTUAL"
    assert captured["payload"]["configured_model"] == "EXAMPLE_CONFIGURED"
    assert captured["payload"]["model_mismatch"] is True


def test_fr7146_run_agent_pins_hello_configured_and_post_launch_actual():
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    start = src.find("def run_agent(")
    assert start >= 0
    chunk = src[start:]
    hello_at = chunk.find("worker_hello_line(kind,")
    digest_at = chunk.find("model=actual or seat_model")
    assert hello_at > 0
    assert digest_at > 0
    assert digest_at < hello_at
    assert "hello_model" in chunk


def test_fr7146_docs_do_not_call_hello_the_launch_actual():
    text = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "is the model the seat actually starts with" not in text
    assert "reports the same value as `model=`" not in text
    assert "hello line (FR #6418 / FR #7187) is the launched actual" in text or "launched actual when known" in text
    assert "digest `start_model` (FR #7084) is the launched process model" in text
