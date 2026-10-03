"""FR #866: seat outbox path stays available after drain (and if parent was missing)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


class FakeIrc:
    shop = "#marchhare"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def say(self, target, text):
        self.sent.append((target, text))
        return True


def test_ensure_outbox_creates_parent_and_file(tmp_path):
    path = tmp_path / "run" / "worker-x" / "outbox.txt"
    assert not path.parent.exists()
    out = bw.ensure_outbox(path)
    assert out == path
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == ""


def test_drain_recreates_empty_outbox(tmp_path):
    path = tmp_path / "outbox.txt"
    path.write_text("PRIVMSG #marchhare :DONE FR o/r#1 https://example/pull/1\n", encoding="utf-8")
    irc = FakeIrc()
    logs: list[str] = []
    n = bw.drain_outbox(path, irc, logs.append)
    assert n == 1
    assert irc.sent and "DONE FR" in irc.sent[0][1]
    # FR #866: file must exist again so agent Set-Content / Add-Content does not PathNotFound.
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == ""


def test_drain_missing_file_still_ensures_path(tmp_path):
    path = tmp_path / "nested" / "outbox.txt"
    irc = FakeIrc()
    n = bw.drain_outbox(path, irc, lambda m: None)
    assert n == 0
    assert path.is_file()
