"""FR #5763: bob airc-replies records UPDATE current / release-lookup-failed too."""
from __future__ import annotations

import json
from pathlib import Path

import irc_agent as ia


def test_fr5763_is_airc_console_reply_matches_update_status_tokens():
    nick = "marchhare_console"
    assert ia.is_airc_console_reply(
        nick,
        "UPDATE accepted id=a00fb6d0 status=scheduled product=airc version=1.0.4",
    )
    assert ia.is_airc_console_reply(
        nick,
        "UPDATE current id=a00fb6d0 product=airc version=1.0.7",
    )
    assert ia.is_airc_console_reply(
        nick,
        "UPDATE release-lookup-failed id=a00fb6d0 product=airc kind=http-404",
    )
    # id-less accepted still recorded (FR #5101 / older schedule replies).
    assert ia.is_airc_console_reply(
        nick,
        "UPDATE accepted status=scheduled product=airc version=1.0.4",
    )
    assert not ia.is_airc_console_reply(nick, "hello UPDATE current")
    assert not ia.is_airc_console_reply("bob-marchhare", "UPDATE current id=a00fb6d0 product=airc")


def test_fr5763_append_records_current_and_release_lookup_failed(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    nick = "marchhare_console"
    lines = [
        "UPDATE current id=deadbeef product=airc version=1.0.7",
        "DONE id=deadbeef exit=0",
        "UPDATE release-lookup-failed id=cafebabe product=airc",
        "DONE id=cafebabe exit=1",
    ]
    for body in lines:
        assert ia.append_airc_reply_jsonl(home, nick, body) is not None
    dest = home / "airc-replies.jsonl"
    rows = [json.loads(x) for x in dest.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 4
    assert rows[0]["body"].startswith("UPDATE current")
    assert rows[2]["body"].startswith("UPDATE release-lookup-failed")
