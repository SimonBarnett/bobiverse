"""FR #995: successful outbox drains must log ``outbox: sent PRIVMSG #<shop> (...n chars)``."""
from __future__ import annotations

import bob_worker as bw


class FakeIrc:
    shop = "#win-mpre8vi4u6u"

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.sent: list[tuple[str, str]] = []

    def say(self, target, text):
        self.sent.append((target, text))
        return self.ok


def test_drain_logs_sent_line_with_char_count(tmp_path):
    path = tmp_path / "outbox.txt"
    body = "DONE FR SimonBarnett/bobiverse#994 https://github.com/SimonBarnett/bobiverse/pull/1004"
    path.write_text(f"PRIVMSG #win-mpre8vi4u6u :{body}\n", encoding="utf-8")
    logs: list[str] = []
    n = bw.drain_outbox(path, FakeIrc(), logs.append)
    assert n == 1
    hit = [m for m in logs if m.startswith("outbox: sent PRIVMSG ")]
    assert hit, logs
    assert f"outbox: sent PRIVMSG #win-mpre8vi4u6u ({len(body)} chars)" in hit[0]
    assert body[:40] in hit[0]
    assert "password=" not in hit[0].lower()


def test_drain_logs_plain_line_as_shop_privmsg(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text("hello shop\n", encoding="utf-8")
    logs: list[str] = []
    assert bw.drain_outbox(path, FakeIrc(), logs.append) == 1
    assert any(
        m.startswith("outbox: sent PRIVMSG #win-mpre8vi4u6u (10 chars)") and "hello shop" in m
        for m in logs
    ), logs


def test_drain_redacts_secrets_in_sent_log(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text("PRIVMSG #win-mpre8vi4u6u :note password=hunter2 keep going\n", encoding="utf-8")
    logs: list[str] = []
    assert bw.drain_outbox(path, FakeIrc(), logs.append) == 1
    hit = [m for m in logs if m.startswith("outbox: sent ")][0]
    assert "hunter2" not in hit
    assert "password=<redacted>" in hit


def test_drain_does_not_log_sent_when_say_fails(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text("PRIVMSG #win-mpre8vi4u6u :ACK FR o/r#1\n", encoding="utf-8")
    logs: list[str] = []
    assert bw.drain_outbox(path, FakeIrc(ok=False), logs.append) == 0
    assert not any(m.startswith("outbox: sent ") for m in logs), logs
