"""FR #6409: worker reports build SHA in hello, DONE, and digest activity."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import done_usage  # noqa: E402


class _FakeIrc:
    shop = "#marchhare"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def say(self, target: str, text: str) -> bool:
        self.sent.append((target, text))
        return True


def test_short_build_sha_unknown_when_meta_missing(monkeypatch):
    monkeypatch.setattr(bw, "get_source_commit", lambda: "unknown")
    assert bw.short_build_sha() == "unknown"
    assert bw.short_build_sha("") == "unknown"
    assert bw.short_build_sha(None) == "unknown"


def test_short_build_sha_truncates_full_commit():
    assert bw.short_build_sha("abcdef0123456789deadbeef") == "abcdef012345"


def test_worker_hello_line_includes_build():
    line = bw.worker_hello_line("grok", build="abc1234def56")
    assert line.startswith("worker ready ")
    assert "kind=grok" in line
    assert "build=abc1234def56" in line


def test_worker_hello_line_fallback_unknown(monkeypatch):
    monkeypatch.setattr(bw, "get_source_commit", lambda: "unknown")
    line = bw.worker_hello_line("cursor")
    assert "build=unknown" in line
    assert "kind=cursor" in line


def test_enrich_done_includes_worker_build(monkeypatch):
    monkeypatch.setattr(bw, "get_source_commit", lambda: "feedface01234567")
    usage = {
        "model": "xai/grok-4.5-build",
        "tokens_in": 1,
        "tokens_out": 2,
        "tokens_cached": None,
        "tokens_unknown": False,
    }
    out = done_usage.enrich_done_payload(
        "DONE FR o/r#1 https://github.com/o/r/pull/1",
        usage,
        worker_build=bw.short_build_sha(),
    )
    assert "model=xai/grok-4.5-build" in out
    assert "tokens_in=1" in out
    assert "worker_build=feedface0123" in out


def test_enrich_done_worker_build_unknown_when_missing():
    out = done_usage.enrich_done_payload(
        "DONE MRB o/r#2 PASS https://github.com/o/r/pull/2",
        {"tokens_unknown": True},
        worker_build=None,
    )
    assert "tokens=unknown" in out
    assert "worker_build=unknown" in out


def test_drain_outbox_enriches_done_with_worker_build(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bw, "get_source_commit", lambda: "deadbeefcafebabe")

    class _Sup:
        kind = "grok"
        cwd = str(tmp_path)
        sessions: list[str] = []
        sessions_root = tmp_path
        run_dir = tmp_path

        def measure_done_usage(self):
            return {"tokens_unknown": True}

        def enrich_done_line(self, payload: str) -> str:
            return done_usage.enrich_done_payload(
                payload,
                self.measure_done_usage(),
                worker_build=bw.short_build_sha(),
            )

    outbox = tmp_path / "outbox.txt"
    outbox.write_text(
        "PRIVMSG #marchhare :DONE FR o/r#9 https://github.com/o/r/pull/9\n",
        encoding="utf-8",
    )
    irc = _FakeIrc()
    logs: list[str] = []
    n = bw.drain_outbox(
        outbox,
        irc,
        logs.append,
        enrich_line=_Sup().enrich_done_line,
    )
    assert n == 1
    _tgt, text = irc.sent[0]
    assert "DONE FR o/r#9" in text
    assert "worker_build=deadbeefcafe" in text
    assert "tokens=unknown" in text


def test_post_digest_seat_kind_includes_worker_build(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_post(url: str, payload: dict, log=None):
        captured["url"] = url
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    monkeypatch.setattr(bw, "get_source_commit", lambda: "0123456789abcdef")
    ok = bw.post_digest_seat_kind(
        machine="marchhare",
        pid=21352,
        nick="marchhare-21352",
        kind="grok",
        worker_build=bw.short_build_sha(),
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    assert captured["payload"]["worker_build"] == "0123456789ab"
    assert captured["payload"]["kind"] == "grok"


def test_post_digest_seat_kind_worker_build_unknown(monkeypatch):
    captured: dict[str, Any] = {}

    def _fake_post(url: str, payload: dict, log=None):
        captured["payload"] = dict(payload)
        return True

    monkeypatch.setattr(bw, "_http_post_json", _fake_post)
    ok = bw.post_digest_seat_kind(
        machine="marchhare",
        pid=1,
        kind="cursor",
        url="https://example.test/bob/v1/report",
    )
    assert ok is True
    assert captured["payload"]["worker_build"] == "unknown"


def test_docs_mention_worker_build():
    text = (ROOT / "bob" / "docs" / "bob-worker.md").read_text(encoding="utf-8")
    assert "worker_build=" in text
    assert "build=" in text
