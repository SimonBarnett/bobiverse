"""FR #1546: bob ear appends *_console Query replies to home/airc-replies.jsonl."""
from __future__ import annotations

import json
from pathlib import Path

import irc_agent as ia


def test_is_airc_console_reply_matches_out_err_done():
    assert ia.is_airc_console_reply("win-mpre8vi4u6u_console", "out id=abcd1234 seq=1 ping")
    assert ia.is_airc_console_reply("marchhare_console", "err id=abcd1234 seq=2 boom")
    assert ia.is_airc_console_reply("ionos_console", "DONE id=abcd1234 exit=0")
    assert not ia.is_airc_console_reply("bob-ionos", "out id=abcd1234 seq=1 x")
    assert not ia.is_airc_console_reply("win-mpre8vi4u6u_console", "hello there")
    assert not ia.is_airc_console_reply("someone", "DONE id=abcd1234 exit=0")


def test_append_airc_reply_jsonl_writes_correlated_lines(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    p = ia.append_airc_reply_jsonl(home, "tm_console", "out id=deadbeef seq=1 hi")
    assert p is not None and p.is_file()
    assert p.name == "airc-replies.jsonl"
    ia.append_airc_reply_jsonl(home, "tm_console", "DONE id=deadbeef exit=0")
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 2
    assert rows[0]["from"] == "tm_console"
    assert rows[0]["body"].startswith("out id=deadbeef")
    assert rows[1]["body"] == "DONE id=deadbeef exit=0"
    assert "ts" in rows[0]


def test_append_skips_non_console(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    assert ia.append_airc_reply_jsonl(home, "bob-tm", "out id=abcd1234 seq=1 x") is None
    assert not (home / "airc-replies.jsonl").exists()
